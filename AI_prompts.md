# AI Prompts — Campus Customs Multi-Agent Operations (HW5)

This file lists the prompts we gave our AI coding assistant (Claude Code) while building the project, in order. Each section has the problem number and title and the prompt in our own words. When a first attempt was missing something or didn't work, the follow-up prompt is listed after it with a short note on what was lacking.

## Project kickoff

**Prompt:**

> For HW5 we are building Campus Customs Multi-Agent Operations, a team of AI agents that helps run the Campus Customs shop. Open tickets (customer orders, inventory problems, rent, unpaid bills, discount requests, other shop issues) arrive on a board. We are building three connected parts: an MCP server, a FastAPI backend that runs the multi-agent team, and a React dashboard where we can watch the agents work and approve requests.
>
> The team has five fully connected agents, and any of them can delegate to any other. **Boss** reads each ticket, routes and coordinates the work, and makes final decisions. **Inventory** checks stock by SKU and size, finds shortages, and picks a vendor to restock. **Accounting** watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval. **Facilities** handles leases, rent, and other shop-space issues. **Customer Service** drafts messages to customers.
>
> Unzip the provided `data/campus_customs.db` and leave it unchanged. Our tools work on a copy, `data/campus_customs_new.db`. Shop rules: `desk.date_today` is the current date and decides what is overdue. Vendor lead times come from the `vendors` table. A vendor with an open unpaid invoice won't ship. Every payment needs human approval. A payment is refused if there isn't enough cash, so the balance can never go negative. Cash only goes out. The working database is reset to the original before every full run. Customer and vendor messages are drafts that stay on the board and are never sent.
>
> Every agent uses only `gpt-6-luna` through Portkey with our `PORTKEY_API_KEY`. No other model can appear anywhere. We'll go one problem at a time, keep earlier work, and only rebuild what doesn't work.

## Problem 1 — Vibe coder prompts

**Prompt:**

> Create `AI_prompts.md` at the start of the project and keep it updated as we work. For each problem, record the problem number, its title, and the prompt we used, in our own words. If we needed a follow-up prompt because something was missing or didn't work, include that too, with a short explanation of what the first attempt lacked.

## Problem 2 — Understand the database and tickets

**Prompt:**

> Before building agents, go through every table and field in `data/campus_customs.db` (desk, tickets, inventory, pricing, vendors, leases, cash_accounts, payments, invoices). Study tickets 101, 102, and 103 and work out which database information each one needs. Copy the original to `data/campus_customs_new.db`, which will be our working database from now on, and leave `campus_customs.db` unchanged. Start `output/harness.md`: list each table and its fields, and briefly explain why that information matters to our agents. Remember that `desk.date_today` is the shop's current date.

## Problem 3 — Build the MCP server

**Prompt:**

> Build an MCP server with FastMCP in `mcp_server/` that connects to our working database, `data/campus_customs_new.db`. Create three useful tools that help the agents solve tickets 101, 102, and 103 using real data from the database. Follow the shop rules: use `desk.date_today`, take vendor information from the `vendors` table, and remember that vendors won't ship while they have an unpaid invoice. Update `output/harness.md` with each tool, the tables it uses, the ticket it helps with, and why it's useful. Also write `mcp_server/README.md` explaining what the server does, which database it uses, and what the three tools do. We don't need to connect or run the server yet.

## Problem 4 — Connect and smoke-test the MCP server

**Prompt:**

> Connect our MCP server to the vibe coder by adding its configuration to `.mcp.json`. Test each of the three MCP tools against `data/campus_customs_new.db` and save the results to `output/mcp_smoke.json`. For each test, record the prompt we used, the MCP tool that was called, and the output we got back. Make sure the results match the real data in our database.

## Problem 5 — Build the multi-agent team

**Prompt:**

> Build the Campus Customs Multi-Agent Operations team with PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. Boss reads each ticket and decides which agents actually need to work on it, and it shouldn't call every agent automatically. Any agent can delegate to another agent whose expertise is needed. Give each agent its own prompt file in `backend/prompts/`, specific to its responsibilities and our shop rules. Every agent uses only `gpt-6-luna` through Portkey. The agents get database information through the MCP server; add MCP tools if they need more to solve tickets 101, 102, and 103. Enforce the shop rules: `desk.date_today` is today, lead times come from `vendors`, no shipping while an invoice is unpaid, all payments need human approval, cash can't go negative, cash only goes out, and communications are drafts only. Agents append their activity to `output/audit_trail.json` without deleting earlier entries. Update `output/harness.md` with the agents, MCP tools, tables, safety rules, and token limits, and update `mcp_server/README.md` with the complete tool list.

## Problem 6 — Predict the ticket workflow

**Prompt:**

> Before running the agents, predict how the team should handle tickets 101, 102, and 103. Create `output/desk_tickets.html` with tabs for Ticket 101, Ticket 102, Ticket 103, Cash, and Reflection, and leave Cash and Reflection empty for now. Give each ticket an Expected section covering which agent Boss contacts first and why, what agent-to-agent delegation we expect, and which MCP tools the agents will use. Base the plan on what each ticket actually needs, without Boss calling every agent. Leave an Actual section on each ticket to fill in after the run.

## Problem 7 — FastAPI backend

**Prompt:**

> Our React dashboard needs a FastAPI backend that works with the agent team. Build routes in `backend/main.py` that let us see tickets 101, 102, and 103 and whether each is open or resolved, pick a ticket and run the agent team on it, see recent agent activity and MCP tool use, approve a payment or purchase, see the current checking balance, and reset `data/campus_customs_new.db` back to the original values. Every payment needs human approval: agents can prepare a payment but can't complete it until we approve. If there isn't enough cash, refuse the payment so the balance never goes negative. Update `output/harness.md` with the API routes and a short explanation of each.

## Problem 8 — React operations dashboard

**Prompt:**

> Build a dashboard in `frontend/` with React, Vite, and TypeScript, connected to our FastAPI backend, that feels like the Campus Customs operations desk and lets us watch the agent team work. It should show tickets 101, 102, and 103 and whether each is open or resolved. It should let us select a ticket and start the team, and show what each agent is doing while it works, the delegations and tool use, and a summary of what each agent did. It should let us approve payments or purchases when human approval is needed, show the current checking balance, and update it after an approved payment. Make it polished and creative, so it looks like a real operations desk rather than a default Vite site, and make Boss, Inventory, Accounting, Facilities, and Customer Service easy to tell apart. Write `output/design.md` explaining our design choices, how we show agent activity, ticket status, and cash, and why we designed it this way.

## Problem 9 — Clean run: resolve tickets 101–103

**Prompt:**

> Do a clean run and resolve tickets 101, 102, and 103. First reset `data/campus_customs_new.db` to the original values and record the starting checking balance. Then use the dashboard to run each ticket until all three are resolved, with only `gpt-6-luna` through Portkey for every agent, following all the shop rules (desk date, vendor lead times, no shipping while an invoice is unpaid, human approval for every payment, refuse payments we can't afford, no negative cash, cash only goes out, no real emails or vendor contact). In `output/desk_tickets.html`, fill in each ticket's Actual section with which agents worked on it, who delegated to whom, and which MCP tools were used, keeping the Expected sections for comparison. Fill in the Cash tab with the starting balance, the cash change from each ticket and why, and the final balance, which must match `cash_accounts` in the working database. Create `output/resolved_tickets.json` with the final results of all three tickets and `output/resolved_board.html` with dashboard screenshots after each ticket is resolved. Keep appending real agent activity to `output/audit_trail.json` and finish updating `output/harness.md`.

## Problem 10 — Reflection

**Prompt:**

> Now that the team has run all three tickets, evaluate how well the system worked by filling in the Reflection tab of `output/desk_tickets.html`, using what actually happened in tickets 101–103 and our Cash results as evidence. Discuss how well the agents handled each ticket and why, how Actual compared with Expected, where delegation was effective, where multiple agents added unnecessary complexity, and which parts one agent with tools could have handled more simply. Give three new Campus Customs problems the current team could solve, three it couldn't, and the extra agents or MCP tools those would need. Keep it specific to our system and the tickets we ran, not a generic explanation of multi-agent AI.

## Problem 11 — Submission

**Prompt:**

> Prepare the project for submission: put it in the homework folder and push it to a public GitHub repo whose URL we'll submit on Canvas. Don't upload the real `.env` or API key; include `.env.example` with placeholders only. Include both `data/campus_customs.db` and `data/campus_customs_new.db`, plus all required files (AI_prompts.md, requirements.txt, .env.example, .gitignore, .mcp.json, README.md, data/, mcp_server/, frontend/, backend/, the five agent prompts, and the output files). Update README.md with instructions for setup, resetting the working DB, starting the MCP server, the FastAPI backend and the React frontend, and doing a clean run of tickets 101–103. Save the public repo URL in `output/github_url.txt`, and before submitting check that the real API key isn't anywhere in the repo and that all required files are present.
