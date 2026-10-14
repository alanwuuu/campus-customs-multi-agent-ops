"""Campus Customs Multi-Agent Operations — FastAPI backend.

Routes for the React dashboard: list tickets, run the agent team on a ticket,
watch agent / MCP activity, approve or reject payments and purchase orders,
check the cash balance, and reset the working database.

Payments: agents can only queue approval requests (via MCP). Money moves only
through POST /api/approvals/{id}/approve, which calls shop_db.decide_approval;
that function refuses anything that would make the balance negative.

Run (from HW5/):  .venv/Scripts/python backend/main.py   -> http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

HW5_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW5_DIR))
sys.path.insert(0, str(HW5_DIR / "mcp_server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import agents  # noqa: E402
import audit  # noqa: E402
import shop_db  # noqa: E402
from reset_db import reset_working_db  # noqa: E402

app = FastAPI(title="Campus Customs Multi-Agent Operations", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One agent run at a time: runs share one MCP server process and one cash balance,
# and a reset must never happen in the middle of a run.
_run_lock = asyncio.Lock()
_runs: dict[str, dict] = {}  # run_id -> status record (in memory; the audit trail is the durable log)


class DecisionBody(BaseModel):
    approver: str = Field(min_length=1, description="Name of the human approving or rejecting")
    note: str = ""


class RunAllBody(BaseModel):
    reset_first: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _approval_rows(where: str = "", params: tuple = ()) -> list[dict]:
    with closing(shop_db.connect()) as conn:
        rows = conn.execute(f"SELECT * FROM approval_requests {where} ORDER BY id DESC", params).fetchall()
        return [shop_db._approval_dict(r) for r in rows]


# ---------------------------------------------------------------- health

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": agents.MODEL_NAME, "database": shop_db.DB_PATH.relative_to(HW5_DIR).as_posix(),
            "agent_running": _run_lock.locked()}


# ---------------------------------------------------------------- tickets

@app.get("/api/tickets")
def list_tickets() -> dict:
    """All tickets with their status (open / in_progress / waiting_approval / blocked / resolved)."""
    with closing(shop_db.connect()) as conn:
        tickets = [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY id")]
        pending = {r["ticket_id"]: r["n"] for r in conn.execute(
            "SELECT ticket_id, COUNT(*) AS n FROM approval_requests WHERE status='pending' GROUP BY ticket_id")}
        drafts = {r["ticket_id"]: r["n"] for r in conn.execute(
            "SELECT ticket_id, COUNT(*) AS n FROM drafts GROUP BY ticket_id")}
        today = shop_db.today(conn).isoformat()
    for t in tickets:
        t["is_resolved"] = t["status"] == "resolved"
        t["pending_approvals"] = pending.get(t["id"], 0)
        t["drafts"] = drafts.get(t["id"], 0)
    return {"date_today": today, "tickets": tickets}


@app.get("/api/tickets/{ticket_id}")
def ticket_detail(ticket_id: int) -> dict:
    """One ticket with linked product / invoice / lease, its approval requests and its drafts (full text)."""
    ctx = shop_db.get_ticket_context(ticket_id)
    if "error" in ctx:
        raise HTTPException(404, ctx["error"])
    with closing(shop_db.connect()) as conn:
        ctx["drafts"] = [dict(r) for r in conn.execute("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id",
                                                       (ticket_id,))]
    ctx["runs"] = [r for r in _runs.values() if ticket_id in r["ticket_ids"]]
    return ctx


async def _execute(run_id: str, ticket_ids: list[int], reset_first: bool) -> None:
    rec = _runs[run_id]
    try:
        async with _run_lock:
            if reset_first:
                reset_working_db()
                audit.log("database_reset", run_id=run_id, agent="human",
                          detail="campus_customs_new.db restored from campus_customs.db before full run")
            if not ticket_ids:  # full run: every open ticket after the reset
                ticket_ids = [t["id"] for t in shop_db.get_open_tickets()["tickets"]]
                rec["ticket_ids"] = ticket_ids
            rec["status"] = "running"
            for tid in ticket_ids:
                rec["current_ticket"] = tid
                outcome = await agents.run_ticket(tid, run_id=run_id)
                rec["outcomes"].append(outcome.model_dump())
        rec["status"] = "finished"
    except Exception as exc:  # surfaced to the dashboard; details are also in the audit trail
        rec["status"] = "failed"
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        rec["current_ticket"] = None
        rec["finished_at"] = _now()


def _start_run(ticket_ids: list[int], reset_first: bool) -> dict:
    if _run_lock.locked():
        raise HTTPException(409, "The agent team is already working on a run; wait for it to finish.")
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {"run_id": run_id, "ticket_ids": ticket_ids, "status": "queued", "current_ticket": None,
                     "outcomes": [], "error": None, "started_at": _now(), "finished_at": None,
                     "reset_first": reset_first}
    asyncio.get_running_loop().create_task(_execute(run_id, ticket_ids, reset_first))
    return _runs[run_id]


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int) -> dict:
    """Start the agent team on one ticket (Boss decides who works on it). Poll /api/runs/{run_id}."""
    if "error" in shop_db.get_ticket_context(ticket_id):
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    return _start_run([ticket_id], reset_first=False)


@app.post("/api/run-all", status_code=202)
async def run_all(body: RunAllBody = RunAllBody()) -> dict:
    """Full run: reset the working DB to the original values (default), then run every open ticket in order."""
    return _start_run([], reset_first=body.reset_first)


@app.get("/api/runs")
def list_runs() -> dict:
    return {"agent_running": _run_lock.locked(),
            "runs": sorted(_runs.values(), key=lambda r: r["started_at"], reverse=True)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if run_id not in _runs:
        raise HTTPException(404, f"Run {run_id} not found (runs are kept in memory until the server restarts)")
    return _runs[run_id]


# ---------------------------------------------------------------- activity

@app.get("/api/activity")
def activity(limit: int = Query(50, ge=1, le=500), ticket_id: int | None = None, run_id: str | None = None,
             event: str | None = None) -> dict:
    """Most recent audit-trail events (agent steps, delegations, MCP tool calls, approvals, resets), newest first."""
    events = audit.read_all()
    if ticket_id is not None:
        events = [e for e in events if e.get("ticket_id") == ticket_id]
    if run_id:
        events = [e for e in events if e.get("run_id") == run_id]
    if event:
        events = [e for e in events if e.get("event") == event]
    return {"total": len(events), "events": list(reversed(events[-limit:]))}


@app.get("/api/drafts")
def drafts(ticket_id: int | None = None) -> dict:
    """Message drafts written by agents. They are never sent."""
    with closing(shop_db.connect()) as conn:
        sql, params = "SELECT * FROM drafts", ()
        if ticket_id is not None:
            sql, params = sql + " WHERE ticket_id = ?", (ticket_id,)
        return {"drafts": [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", params)]}


# ---------------------------------------------------------------- approvals (human only)

@app.get("/api/approvals")
def approvals(status: Literal["pending", "approved", "rejected", "refused", "all"] = "pending") -> dict:
    """Payment and purchase-order requests prepared by agents."""
    rows = _approval_rows() if status == "all" else _approval_rows("WHERE status = ?", (status,))
    return {"cash_balance": shop_db.get_cash_position()["cash_balance"], "requests": rows}


def _decide(request_id: int, approve: bool, body: DecisionBody) -> dict:
    if _run_lock.locked():
        raise HTTPException(409, "Wait for the current agent run to finish before approving.")
    try:
        result = shop_db.decide_approval(request_id, approve, body.approver.strip(), body.note)
    except ValueError as exc:  # not found / already decided
        raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    if "error" in result:  # e.g. PO still blocked by an unpaid vendor invoice; stays pending
        raise HTTPException(409, result["error"])

    req = _approval_rows("WHERE id = ?", (request_id,))[0]
    audit.log(f"approval_{result['status']}", ticket_id=req["ticket_id"], agent="human",
              approver=body.approver, request_id=request_id, kind=req["kind"], payee=req["payee"],
              amount=req["amount"], result=result["result"], cash_balance=result["cash_balance"])
    if req["ticket_id"] is not None:  # leave a trace on the ticket; status is still Boss's call
        with closing(shop_db.connect()) as conn:
            t = conn.execute("SELECT notes FROM tickets WHERE id = ?", (req["ticket_id"],)).fetchone()
            if t is not None:
                stamp = (f"[{shop_db.today(conn).isoformat()} human:{body.approver}] request #{request_id} "
                         f"({req['kind']} ${req['amount']:,.2f}) {result['status']}: {result['result']}")
                conn.execute("UPDATE tickets SET notes = ? WHERE id = ?",
                             (f"{t['notes']}\n{stamp}" if t["notes"] else stamp, req["ticket_id"]))
                conn.commit()
    return {**result, "request": req}


@app.post("/api/approvals/{request_id}/approve")
def approve(request_id: int, body: DecisionBody) -> dict:
    """Human approves a queued payment / PO. Refused (no money moves) if it would make cash negative,
    and rejected with 409 if it is a PO to a vendor that still has an unpaid invoice."""
    return _decide(request_id, True, body)


@app.post("/api/approvals/{request_id}/reject")
def reject(request_id: int, body: DecisionBody) -> dict:
    """Human rejects a queued payment / PO. No money moves."""
    return _decide(request_id, False, body)


# ---------------------------------------------------------------- cash

@app.get("/api/cash")
def cash() -> dict:
    """Current checking balance, obligations by due date, pending requests, and recent payments."""
    pos = shop_db.get_cash_position()
    checking = next((a for a in pos["accounts"] if a["name"] == shop_db.CASH_ACCOUNT), None)
    with closing(shop_db.connect()) as conn:
        payments = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY id DESC")]
    return {**pos, "checking_balance": checking["balance"] if checking else 0.0, "payments": payments}


# ---------------------------------------------------------------- reset

@app.post("/api/reset")
def reset() -> dict:
    """Restore data/campus_customs_new.db from the original data/campus_customs.db (original is never modified).
    The audit trail is kept; a reset event is appended."""
    if _run_lock.locked():
        raise HTTPException(409, "Cannot reset while the agent team is running.")
    path = reset_working_db()
    audit.log("database_reset", agent="human", detail="campus_customs_new.db restored from campus_customs.db")
    pos = shop_db.get_cash_position()
    return {"ok": True, "database": path.relative_to(HW5_DIR).as_posix(), "checking_balance": pos["cash_balance"],
            "open_tickets": len(shop_db.get_open_tickets()["tickets"])}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)  # single process, no reloader
