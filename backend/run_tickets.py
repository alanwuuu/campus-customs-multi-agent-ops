"""Run the agent team on tickets from the command line.

  python backend/run_tickets.py 101          # one ticket, on the current working DB
  python backend/run_tickets.py --all        # full run: reset working DB, then every open ticket
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

HW5_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW5_DIR))
sys.path.insert(0, str(HW5_DIR / "mcp_server"))

import audit  # noqa: E402
import shop_db  # noqa: E402
from agents import run_ticket  # noqa: E402
from reset_db import reset_working_db  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("tickets", nargs="*", type=int)
    p.add_argument("--all", action="store_true", help="reset the working DB, then run every open ticket")
    a = p.parse_args()

    run_id = uuid.uuid4().hex[:12]
    if a.all:
        reset_working_db()
        audit.log("database_reset", run_id=run_id, detail="campus_customs_new.db restored from campus_customs.db")
        ids = [t["id"] for t in shop_db.get_open_tickets()["tickets"]]
    else:
        ids = a.tickets
    if not ids:
        p.error("give ticket ids or --all")

    for tid in ids:
        outcome = await run_ticket(tid, run_id=run_id)
        print(json.dumps(outcome.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
