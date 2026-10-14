# Campus Customs Multi-Agent Operations (HW5)

Campus Customs Multi-Agent Operations is a team of AI agents that helps run the Campus Customs shop on Chapel Street. It has three connected parts:

- **MCP server** (`mcp_server/`, FastMCP): the only way the agents read or change the shop database. The shop rules are enforced here in code.
- **FastAPI backend** (`backend/`): a PydanticAI team of five agents (Boss, Inventory, Accounting, Facilities, Customer Service) with full delegation between them. It also exposes the routes for ticket runs, human approvals, cash and resets.
- **React dashboard** (`frontend/`, React + Vite + TypeScript): the "Ops Desk", where you watch the agents work and approve payments.

Every agent uses only **`gpt-6-luna` through Portkey**.

## Project layout

```
AI_prompts.md          prompts used to build the project
requirements.txt       Python dependencies
.env.example           placeholder for PORTKEY_API_KEY
.mcp.json              MCP server config (campus-customs, stdio)
reset_db.py            restore the working DB from the original
data/
  campus_customs.db       original database (never modified)
  campus_customs_new.db   working database (final state of the clean run)
mcp_server/            server.py, shop_db.py, smoke_test.py, README.md
backend/               main.py (FastAPI), agents.py, audit.py, run_tickets.py,
                       export_results.py, prompts/ (boss, inventory, accounting,
                       facilities, customer_service)
frontend/              React + Vite + TypeScript dashboard
output/                harness.md, mcp_smoke.json, audit_trail.json, desk_tickets.html,
                       design.md, resolved_tickets.json, resolved_board.html,
                       screenshots/, github_url.txt
```

## 1. Set up the environment

You need Python 3.12+ (developed on 3.14) and Node 20+ (developed on 24).

Create a virtual environment and install the Python dependencies:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

Install the frontend dependencies:

```bash
npm --prefix frontend install
```

Then create your `.env` and put your Portkey key in it:

```bash
cp .env.example .env
```

On macOS and Linux, the Python path is `.venv/bin/python` instead of `.venv/Scripts/python`.

## 2. Reset the working database

```bash
.venv/Scripts/python reset_db.py
```

This copies `data/campus_customs.db` over `data/campus_customs_new.db`, which sets cash back to $3,400 and all tickets back to open. The original database is never written to. You can also use **Reset DB** on the dashboard, which calls `POST /api/reset`.

## 3. Start the MCP server

The backend launches the MCP server automatically from `.mcp.json`, so you don't need to start it yourself to run the agents. To run it on its own over stdio:

```bash
.venv/Scripts/python mcp_server/server.py
```

To test all of its tools through the real MCP protocol (this writes `output/mcp_smoke.json`):

```bash
.venv/Scripts/python mcp_server/smoke_test.py
```

Claude Code also picks up the `campus-customs` server from `.mcp.json` when started in this folder.

## 4. Start the FastAPI backend

```bash
.venv/Scripts/python backend/main.py
```

It serves http://127.0.0.1:8000, with interactive docs at `/docs`. It runs as a single process without the auto-reloader.

## 5. Start the React frontend

```bash
npm --prefix frontend run dev
```

Open http://localhost:5173. Vite forwards `/api` requests to the backend on port 8000, so the backend has to be running.

## 6. Clean run of tickets 101, 102 and 103

1. Start the backend (step 4) and the frontend (step 5).
2. Click **Reset DB** in the dashboard and confirm that checking shows **$3,400.00**.
3. Select **#101** on the ticket rail and click **Run agents**. Watch the agent stations, hand-off map and live wire.
4. When requests appear in the **Approval tray**, type your name under *Signing as* and approve them. Approve vendor invoice 501 first, because the vendor won't ship until it's paid. The register refuses any payment larger than the cash balance.
5. Click **Run agents** again so Boss can confirm the approvals and mark the ticket **Resolved**.
6. Repeat steps 3–5 for **#102** and **#103**. Ticket 103 needed only one run in our clean run.
7. Export the results:

   ```bash
   .venv/Scripts/python backend/export_results.py
   ```

   This writes `output/resolved_tickets.json`, including the rule checks.

From the command line, `backend/run_tickets.py --all` resets the database and runs every open ticket once. The human approvals still happen on the dashboard or through `POST /api/approvals/{id}/approve`.

**Our clean-run result:** $3,400 → $2,552 (ticket 101: invoice 501 and a 1-tee restock) → $152 (ticket 102: rent) → $152 (ticket 103: partial fill, no restock affordable). All three tickets ended resolved. See `output/desk_tickets.html` and `output/resolved_board.html`.

## Shop rules (enforced in `mcp_server/shop_db.py`)

- `desk.date_today` (2026-08-31) is today.
- Lead times come from `vendors`.
- A vendor with an open unpaid invoice won't ship.
- Every payment needs human approval. Agents can only queue requests.
- A payment larger than the balance is refused, so cash never goes negative.
- Cash only goes out.
- Messages are drafts only and are never sent.
