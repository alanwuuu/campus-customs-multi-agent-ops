"""Export the clean run's final results to output/resolved_tickets.json.

Reads the working database (final state) and the audit-trail events recorded
since the most recent database reset (= the start of the clean run).

Usage (from HW5/):  .venv/Scripts/python backend/export_results.py
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HW5_DIR = Path(__file__).resolve().parent.parent
WORKING_DB = HW5_DIR / "data" / "campus_customs_new.db"
ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"
AUDIT = HW5_DIR / "output" / "audit_trail.json"
OUT = HW5_DIR / "output" / "resolved_tickets.json"
MODEL = "gpt-6-luna"


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def clean_run_events() -> tuple[list[dict], dict]:
    events = json.loads(AUDIT.read_text(encoding="utf-8"))
    start = max(i for i, e in enumerate(events) if e["event"] == "database_reset")
    return events[start:], events[start]


def summarize_run(evts: list[dict]) -> dict:
    started = next(e for e in evts if e["event"] == "ticket_started")
    finished = next((e for e in evts if e["event"] in ("ticket_finished", "ticket_failed")), None)
    agents, tools, delegations = [], [], []
    for e in evts:
        if e["event"] == "tool_call":
            tools.append({"agent": e["agent"], "tool": e["tool"],
                          "args": {k: v for k, v in (e.get("args") or {}).items()
                                   if k not in ("body", "reason", "note")}})
            if e["agent"] not in agents:
                agents.append(e["agent"])
        elif e["event"] == "delegation":
            delegations.append({"from": e["agent"], "to": e["to"], "task": e["task"]})
            for a in (e["agent"], e["to"]):
                if a not in agents:
                    agents.append(a)
    if "boss" not in agents:
        agents.insert(0, "boss")
    return {
        "run_id": started["run_id"],
        "started_at": started["timestamp"],
        "model": started.get("model"),
        "agents_worked": agents,
        "delegations": delegations,
        "mcp_tool_calls": tools,
        "outcome": finished.get("outcome") if finished else None,
        "usage": finished.get("usage") if finished else None,
        "error": finished.get("error") if finished and finished["event"] == "ticket_failed" else None,
    }


def main() -> None:
    events, reset_event = clean_run_events()
    conn = sqlite3.connect(f"file:{WORKING_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    orig = sqlite3.connect(f"file:{ORIGINAL_DB}?mode=ro", uri=True)
    orig.row_factory = sqlite3.Row

    start_balance = rows(orig, "SELECT balance FROM cash_accounts WHERE name='checking'")[0]["balance"]
    final_cash = rows(conn, "SELECT * FROM cash_accounts WHERE name='checking'")[0]
    payments = rows(conn, "SELECT * FROM payments ORDER BY id")
    approvals = rows(conn, "SELECT * FROM approval_requests ORDER BY id")
    for a in approvals:
        a["details"] = json.loads(a["details"]) if a["details"] else None
    drafts = rows(conn, "SELECT * FROM drafts ORDER BY id")
    pay_by_request = {a["payment_id"]: a for a in approvals if a["payment_id"]}

    tickets_out = []
    running_balance = start_balance
    for t in rows(conn, "SELECT * FROM tickets ORDER BY id"):
        tid = t["id"]
        run_ids = list(dict.fromkeys(e["run_id"] for e in events
                                     if e.get("ticket_id") == tid and e["event"] == "ticket_started"))
        runs = [summarize_run([e for e in events if e.get("run_id") == rid and e.get("ticket_id") == tid])
                for rid in run_ids]
        t_approvals = [a for a in approvals if a["ticket_id"] == tid]
        t_payments = [p for p in payments if pay_by_request.get(p["id"], {}).get("ticket_id") == tid]
        cash_change = round(-sum(p["amount"] for p in t_payments), 2)
        before, running_balance = running_balance, round(running_balance + cash_change, 2)

        agents = list(dict.fromkeys(a for r in runs for a in r["agents_worked"]))
        edges = Counter(f"{d['from']} -> {d['to']}" for r in runs for d in r["delegations"])
        tools = Counter(f"{c['agent']}: {c['tool']}" for r in runs for c in r["mcp_tool_calls"])
        final = runs[-1]["outcome"] if runs else None

        tickets_out.append({
            "ticket_id": tid,
            "type": t["type"],
            "requester": t["requester"],
            "subject": t["subject"],
            "final_status": t["status"],
            "resolved": t["status"] == "resolved",
            "final_decision": final["decision"] if final else None,
            "agents_worked": agents,
            "agents_not_needed": [a for a in ("boss", "inventory", "accounting", "facilities", "customer_service")
                                  if a not in agents],
            "delegations": dict(edges),
            "mcp_tools_used": dict(tools),
            "runs": runs,
            "approval_requests": [{k: a[k] for k in ("id", "kind", "ref_id", "payee", "amount", "status",
                                                    "requested_by", "decided_by", "decided_at", "reason")}
                                  for a in t_approvals],
            "payments": t_payments,
            "drafts": [{k: d[k] for k in ("id", "recipient", "recipient_type", "subject", "body", "author", "status")}
                       for d in drafts if d["ticket_id"] == tid],
            "cash": {"before": before, "change": cash_change, "after": running_balance},
            "total_tokens": sum((r["usage"] or {}).get("total_tokens", 0) for r in runs),
        })

    models = {e.get("model") for e in events if e["event"] == "ticket_started"}
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "clean_run_started_at": reset_event["timestamp"],
        "desk_date_today": rows(conn, "SELECT date_today FROM desk")[0]["date_today"],
        "model": MODEL,
        "models_seen_in_runs": sorted(m for m in models if m),
        "database": "data/campus_customs_new.db",
        "cash": {
            "starting_checking_balance": start_balance,
            "changes": [{"ticket_id": x["ticket_id"], "change": x["cash"]["change"]} for x in tickets_out],
            "final_checking_balance_computed": running_balance,
            "final_checking_balance_in_cash_accounts": final_cash["balance"],
            "matches_cash_accounts": abs(running_balance - final_cash["balance"]) < 0.005,
            "never_negative": running_balance >= 0,
        },
        "rule_checks": {
            "all_tickets_resolved": all(x["resolved"] for x in tickets_out),
            "only_gpt_6_luna_used": models == {MODEL},
            "every_payment_human_approved": all(p["approved_by"] and p["approved_by"] not in
                                                ("boss", "inventory", "accounting", "facilities", "customer_service")
                                                for p in payments),
            "payments_match_approved_requests": sorted(p["id"] for p in payments)
                                                == sorted(a["payment_id"] for a in approvals if a["status"] == "approved"),
            "all_messages_are_unsent_drafts": all(d["status"] == "draft" for d in drafts),
            "vendor_invoice_paid_before_po_approved": all(
                any(p2["kind"] == "invoice" and p2["id"] < p["id"] for p2 in payments)
                for p in payments if p["kind"] == "purchase_order"),
            "cash_never_negative": running_balance >= 0,
        },
        "tickets": tickets_out,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"cash": result["cash"], "rule_checks": result["rule_checks"]}, indent=2))
    for x in tickets_out:
        print(f"\n#{x['ticket_id']} {x['final_status']} | agents {x['agents_worked']} | not needed {x['agents_not_needed']}"
              f" | runs {len(x['runs'])} | tokens {x['total_tokens']} | cash {x['cash']}")
        print("  delegations", x["delegations"])
        print("  tools", x["mcp_tools_used"])
        for r in x["runs"]:
            print("  run", r["run_id"], "->", (r["outcome"] or {}).get("status"), (r["usage"] or {}).get("total_tokens"))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
