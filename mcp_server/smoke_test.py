"""Smoke-test the Campus Customs MCP server through the real MCP protocol.

Launches the server exactly as configured in HW5/.mcp.json (stdio), calls
each tool once with the prompt that motivates it, cross-checks the answer
against direct SQL on the working database, and writes output/mcp_smoke.json.

Usage (from HW5/):  .venv/Scripts/python mcp_server/smoke_test.py
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

HW5_DIR = Path(__file__).resolve().parent.parent
DB_PATH = HW5_DIR / "data" / "campus_customs_new.db"
OUT_PATH = HW5_DIR / "output" / "mcp_smoke.json"

TESTS = [
    {
        "prompt": "Use the campus-customs MCP server to pull everything linked to ticket 101 "
                  "so Boss can decide who should work on it.",
        "tool": "get_ticket_context",
        "arguments": {"ticket_id": 101},
    },
    {
        "prompt": "Ticket 103: the Yale AI Club wants 20 CC-HOOD-NAVY hoodies in size M. "
                  "Check stock and, if we are short, which vendor can restock, when, and whether they will ship.",
        "tool": "check_stock_and_restock",
        "arguments": {"sku": "CC-HOOD-NAVY", "size": "M", "qty_needed": 20},
    },
    {
        "prompt": "Ticket 102: rent is due. Show our cash balance against every open invoice and rent "
                  "payment, and tell me what we can afford without going negative.",
        "tool": "get_cash_position",
        "arguments": {},
    },
]


def sql(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def check(label: str, got, expected) -> dict:
    return {"check": label, "tool_value": got, "database_value": expected, "pass": got == expected}


def verify(tool: str, out: dict) -> list[dict]:
    today = sql("SELECT date_today FROM desk")[0][0]
    checks = [check("date_today matches desk.date_today", out["date_today"], today)]

    if tool == "get_ticket_context":
        t = sql("SELECT * FROM tickets WHERE id = 101")[0]
        inv = sql("SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],))[0]
        stock = sql("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (t["sku"], t["size"]))[0][0]
        checks += [
            check("ticket requester", out["ticket"]["requester"], t["requester"]),
            check("tee S on hand", out["product"]["on_hand_in_size"], stock),
            check("linked invoice id", out["invoice"]["id"], inv["id"]),
            check("linked invoice amount", out["invoice"]["amount"], inv["amount"]),
            check("invoice days overdue (date_today - due_date)", out["invoice"]["days_overdue"],
                  (datetime.fromisoformat(today) - datetime.fromisoformat(inv["due_date"])).days),
        ]
    elif tool == "check_stock_and_restock":
        qty = sql("SELECT qty FROM inventory WHERE sku='CC-HOOD-NAVY' AND size='M'")[0][0]
        cost = sql("SELECT unit_cost FROM pricing WHERE sku='CC-HOOD-NAVY'")[0][0]
        v = sql("SELECT * FROM vendors WHERE specialty LIKE '%apparel%'")[0]
        open_inv = [r["id"] for r in sql("SELECT id FROM invoices WHERE vendor_id=? AND status='open'", (v["id"],))]
        r = out["restock"]
        checks += [
            check("hoodie M on hand", out["on_hand"], qty),
            check("shortage = 20 - on hand", out["shortage"], 20 - qty),
            check("vendor from vendors table", r["vendor"], v["name"]),
            check("lead_days from vendors table", r["lead_days"], v["lead_days"]),
            check("PO cost = shortage x unit_cost", r["po_cost"], (20 - qty) * cost),
            check("blocking invoices = vendor's open invoices", [i["id"] for i in r["blocking_invoices"]], open_inv),
            check("vendor_will_ship is false while an invoice is open", r["vendor_will_ship"], not open_inv),
        ]
    elif tool == "get_cash_position":
        bal = sql("SELECT SUM(balance) FROM cash_accounts")[0][0]
        inv_total = sql("SELECT COALESCE(SUM(amount),0) FROM invoices WHERE status='open'")[0][0]
        rent_total = sql("SELECT SUM(monthly_rent) FROM leases")[0][0]
        checks += [
            check("cash balance", out["cash_balance"], bal),
            check("total obligations = open invoices + rent", out["total_obligations"], inv_total + rent_total),
            check("balance after all obligations", out["balance_after_all_obligations"],
                  bal - inv_total - rent_total),
            check("never negative after paying invoice + rent", out["balance_after_all_obligations"] >= 0, True),
        ]
    return checks


async def main() -> None:
    config = json.loads((HW5_DIR / ".mcp.json").read_text())
    server_cfg = config["mcpServers"]["campus-customs"]
    # .mcp.json paths are relative to HW5/; make them absolute for this client.
    server_cfg = {**server_cfg, "command": str(HW5_DIR / server_cfg["command"]),
                  "args": [str(HW5_DIR / a) for a in server_cfg["args"]]}

    results = []
    async with Client({"mcpServers": {"campus-customs": server_cfg}}) as client:
        tools = [t.name for t in await client.list_tools()]
        for test in TESTS:
            res = await client.call_tool(test["tool"], test["arguments"])
            output = res.structured_content
            if isinstance(output, dict) and set(output) == {"result"}:
                output = output["result"]
            checks = verify(test["tool"], output)
            results.append({**test, "output": output, "verification": checks,
                            "all_checks_pass": all(c["pass"] for c in checks)})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mcp_config": ".mcp.json -> campus-customs (stdio: .venv/Scripts/python.exe mcp_server/server.py)",
        "database": "data/campus_customs_new.db",
        "tools_listed_by_server": tools,
        "tests": results,
        "all_tests_pass": all(r["all_checks_pass"] for r in results),
    }
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for r in results:
        print(f"{r['tool']:<26} {'PASS' if r['all_checks_pass'] else 'FAIL'}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
