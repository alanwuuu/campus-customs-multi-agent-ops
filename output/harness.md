# Campus Customs Multi-Agent Operations — Harness

## 1. Database overview

- **Original database:** `data/campus_customs.db`. Read-only reference; never modified.
- **Working database:** `data/campus_customs_new.db`. A byte-for-byte copy of the original (identical SHA-256). All agent tools read and write here. `python reset_db.py` restores it from the original and must be run before every full run.
- **Shop date:** `desk.date_today = 2026-08-31`. This is "today" for every due-date, overdue, and lead-time calculation. Agents must not use the real calendar date.

## 2. Tables and fields

### `desk` (1 row)
| Field | Type | Value / meaning |
|---|---|---|
| `date_today` | TEXT | `2026-08-31`, the shop's current date |
| `notes` | TEXT | Free-form desk notes (currently empty) |

**Why it matters:** This is the shared clock for every agent. Accounting uses it to decide whether an invoice is overdue, Facilities uses it to count days until rent is due, and Inventory adds vendor lead days to it to estimate restock arrival.

### `tickets` (3 rows)
| Field | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Ticket number |
| `type` | TEXT | Category (`customer_order`, `rent_notice`, `price_override`). Boss uses it to route the ticket. |
| `requester` | TEXT | Who raised it (customer, landlord, student org) |
| `subject` | TEXT | Short title |
| `sku`, `size`, `qty` | TEXT, TEXT, INTEGER | Product, size, and quantity requested (when relevant) |
| `lease_id` | INTEGER FK → `leases.id` | Linked lease (rent/space tickets) |
| `invoice_id` | INTEGER FK → `invoices.id` | Linked vendor invoice |
| `status` | TEXT | `open` now; updated as tickets are resolved |
| `notes` | TEXT | Details of the request |
| `created_at` | TEXT | ISO timestamp with timezone (−04:00) |

**Why it matters:** This is the work queue on the board. The foreign keys tell agents which other rows to look up, and `status` is how resolution gets recorded.

### `inventory` (10 rows, PK = `sku` + `size`)
| Field | Type | Meaning |
|---|---|---|
| `sku` | TEXT | Product code |
| `name` | TEXT | Product name |
| `size` | TEXT | S / M / L / XL, or OS (one size) |
| `qty` | INTEGER | Units on hand |
| `location` | TEXT | Aisle in the shop |

Current stock:

| SKU | Name | S | M | L | XL | OS |
|---|---|---|---|---|---|---|
| CC-HOOD-NAVY | Basic Hoodie Big Yale | 4 | 8 | 14 | 6 | |
| CC-TEE-WHITE | Classic Bulldog Tee | **0** | 5 | 3 | 2 | |
| CC-HAT-BLUE | Yale Cap | | | | | 40 |
| CC-MUG-CREST | Crest Mug | | | | | **0** |

**Why it matters:** Inventory checks stock by SKU **and** size, because one size can be out while others are in stock. Shortages start the restock process, and `qty` gets decremented when an order is fulfilled.

### `pricing` (4 rows)
| Field | Type | Meaning |
|---|---|---|
| `sku` | TEXT PK | Product code |
| `unit_cost` | REAL | What the shop pays a vendor per unit |
| `list_price` | REAL | Normal selling price |

| SKU | Cost | List | Margin/unit | Margin % |
|---|---|---|---|---|
| CC-HOOD-NAVY | $22.00 | $58.00 | $36.00 | 62.1% |
| CC-TEE-WHITE | $8.00 | $28.00 | $20.00 | 71.4% |
| CC-HAT-BLUE | $6.00 | $22.00 | $16.00 | 72.7% |
| CC-MUG-CREST | $3.50 | $14.00 | $10.50 | 75.0% |

**Why it matters:** Accounting uses `unit_cost` to price purchase orders and margins to decide how much discount is affordable. Customer Service quotes `list_price` to customers.

### `vendors` (3 rows)
| Field | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Vendor id (referenced by `invoices.vendor_id`) |
| `name` | TEXT | Vendor name |
| `specialty` | TEXT | What they supply |
| `lead_days` | INTEGER | Days from order to delivery |

| id | Name | Specialty | Lead days |
|---|---|---|---|
| 1 | Bulldog Print Co | apparel reprint | 5 |
| 2 | Elm City Gifts | mugs and small goods | 3 |
| 3 | QuickShip CT | local courier | 1 |

**Why it matters:** Inventory matches the product to a vendor by `specialty` and estimates arrival as `date_today + lead_days`. Lead times must come from this table, not be guessed. Before ordering, the vendor's open invoices must be checked, because a vendor with an open unpaid invoice won't ship.

### `leases` (1 row)
| Field | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Lease id |
| `space_name` | TEXT | The space (`Chapel Street shop`) |
| `landlord` | TEXT | `Elm City Properties` |
| `monthly_rent` | REAL | `$2,400.00` |
| `next_due` | TEXT | `2026-09-02` (2 days after `date_today`) |
| `notes` | TEXT | Free-form (empty) |

**Why it matters:** Facilities owns this table. It confirms the rent amount and due date and hands the payment to Accounting. After rent is paid, `next_due` should roll forward one month.

### `cash_accounts` (1 row)
| Field | Type | Meaning |
|---|---|---|
| `name` | TEXT PK | `checking` |
| `balance` | REAL | `$3,400.00` |
| `date` | TEXT | `2026-08-31` (as-of date) |

**Why it matters:** This is the only source of cash. Every payment must be checked against `balance`, and a payment that would make it negative must be refused. No revenue is modeled, so the balance only goes down.

### `payments` (0 rows)
| Field | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Payment id |
| `kind` | TEXT | What was paid (e.g. `invoice`, `rent`, `purchase_order`) |
| `ref_id` | INTEGER | Id of the paid item (invoice id, lease id, …) |
| `amount` | REAL | Amount paid |
| `account` | TEXT | Cash account debited (FK-like to `cash_accounts.name`) |
| `paid_at` | TEXT | When it was paid (shop date) |
| `approved_by` | TEXT | **Required:** the human who approved it |

**Why it matters:** This is the audit trail. A row is written only after a human approves on the dashboard. `approved_by` is NOT NULL, which enforces that rule at the schema level.

### `invoices` (1 row)
| Field | Type | Meaning |
|---|---|---|
| `id` | INTEGER PK | Invoice id |
| `vendor_id` | INTEGER FK → `vendors.id` | Who is owed |
| `amount` | REAL | Amount owed |
| `due_date` | TEXT | Due date |
| `status` | TEXT | `open` or `paid` |
| `description` | TEXT | What was bought |

| id | Vendor | Amount | Due | Status | Description |
|---|---|---|---|---|---|
| 501 | 1 — Bulldog Print Co | $840.00 | 2026-08-28 | open | Rush reprint CC-TEE-WHITE S |

**Why it matters:** Accounting compares `due_date` to `desk.date_today`. Invoice 501 is **3 days overdue**, and because it is open, Bulldog Print Co (the only apparel vendor) won't ship until it's paid.

## 3. Open tickets and the data each one needs

### Ticket 101 — `customer_order`: Tauhid Zaman, 1× CC-TEE-WHITE size S
- **Needed data:** `inventory` (tee S = **0**, so it's out of stock), `vendors` (apparel → Bulldog Print Co, 5 lead days), `invoices` 501 (linked via `invoice_id`: the S reprint is already invoiced but unpaid and overdue), `cash_accounts`, `pricing` (list $28).
- **Considerations:** The order can't be filled from stock. The restock is blocked until invoice 501 ($840) is paid with human approval. If it's paid today, the earliest arrival is 2026-08-31 + 5 days = **2026-09-05**. Customer Service drafts an update for the customer.
- **Agents:** Boss → Inventory → Accounting (invoice 501 payment for approval) → Customer Service (draft).

### Ticket 102 — `rent_notice`: Elm City Properties, lease 1
- **Needed data:** `leases` 1 ($2,400, due **2026-09-02**, 2 days out), `cash_accounts` ($3,400), `payments` (to record it after approval).
- **Considerations:** Rent isn't overdue yet but is due soon. Paying it needs human approval and enough cash.
- **Agents:** Boss → Facilities → Accounting (rent payment for approval).

### Ticket 103 — `price_override`: Yale AI Club, 20× CC-HOOD-NAVY size M, bulk discount
- **Needed data:** `inventory` (hoodie M = **8**, so 12 short), `pricing` (cost $22, list $58, 62% margin), `vendors` (Bulldog Print Co, 5 lead days), `invoices` (501 blocks Bulldog), `cash_accounts`.
- **Considerations:** At list price the order is 20 × $58 = $1,160 against a cost of $440. A discount still leaves room, but it has to keep a positive margin. Restocking 12 units costs 12 × $22 = $264 and is also blocked by invoice 501. Boss makes the final call on the discount, and Customer Service drafts the reply.
- **Agents:** Boss → Inventory → Accounting (margin check, PO for approval) → Customer Service (draft).

### Cash picture across all tickets
| Item | Amount | Running balance |
|---|---|---|
| Starting checking balance | | $3,400.00 |
| Invoice 501 (Bulldog, overdue) | −$840.00 | $2,560.00 |
| Rent, lease 1 (due 09-02) | −$2,400.00 | $160.00 |
| PO: 12× hoodie M restock | −$264.00 | **−$104.00 → must be refused** |

Paying both obligations leaves $160, which isn't enough for the hoodie restock. Agents have to prioritize: the overdue invoice and rent come first, and any payment that would make cash negative is refused. Revenue from the hoodie sale isn't modeled, so it can't be counted on to cover the PO.

## 4. Shop rules (constraints for every agent)
1. `desk.date_today` is today's date and decides what is overdue.
2. Vendor lead times come only from `vendors.lead_days`.
3. A vendor with an open unpaid invoice won't ship new products.
4. Every payment needs human approval before it's recorded.
5. Payments larger than the cash balance are refused, so the balance never goes negative.
6. Cash only goes out; revenue isn't modeled.
7. Reset `campus_customs_new.db` from the original before every full run.
8. Customer and vendor messages are drafts on the board only and are never sent.
9. All agents use only `gpt-6-luna` via Portkey (`PORTKEY_API_KEY`).

## 5. MCP server tools (`mcp_server/server.py`)

The FastMCP server `campus-customs` connects to the working database `data/campus_customs_new.db`. These are the three original read tools. Problem 5 added more (see section 8). All tools compute dates from `desk.date_today`.

| Tool | Tables used | Tickets | Main agent(s) |
|---|---|---|---|
| `get_ticket_context(ticket_id)` | desk, tickets, inventory, pricing, invoices, vendors, leases | 101, 102, 103 | Boss |
| `check_stock_and_restock(sku, size, qty_needed)` | desk, inventory, pricing, vendors, invoices | 101, 103 | Inventory, Accounting |
| `get_cash_position()` | desk, cash_accounts, invoices, vendors, leases, payments | 101, 102, 103 | Accounting, Facilities |

### `get_ticket_context(ticket_id)`
- **What it returns:** the ticket row plus its linked product (stock in the requested size and all sizes, cost, list price, margin), linked invoice (days overdue), and linked lease (days until rent is due).
- **Why it's useful:** Boss gets the whole picture in one call and can route the ticket correctly. For example, 101 is linked to overdue invoice 501, 102 to lease 1 due in 2 days, and 103 shows 8 hoodies in stock against 20 requested, with a 62% margin.

### `check_stock_and_restock(sku, size, qty_needed)`
- **What it returns:** on-hand quantity, how much can be filled now, and the shortage. For a shortage it also returns the vendor chosen by `vendors.specialty`, `lead_days`, the PO cost (`shortage × unit_cost`), and the ETA (`date_today + lead_days`). When the vendor has open invoices, it returns `vendor_will_ship = false` along with those invoices.
- **Why it's useful:** it applies the "no shipping while an invoice is unpaid" rule at the data level. For 101 (tee S, 0 on hand) and 103 (hoodie M, 12 short), it shows that Bulldog Print Co is blocked by invoice 501 ($840, 3 days overdue). Paying it today would bring the earliest arrival to 2026-09-05. The 12-hoodie PO costs $264.

### `get_cash_position()`
- **What it returns:** the checking balance and all open invoices and rent, sorted by due date, with overdue flags, the running balance if paid in order, and whether each payment is affordable. It also returns recent payments.
- **Why it's useful:** Accounting can prepare payments for human approval and refuse any that would make cash negative. Today it shows $3,400 − $840 (invoice 501) − $2,400 (rent) = $160 left, which isn't enough for the $264 hoodie PO.

## 6. MCP connection and smoke test

- **Config:** `.mcp.json` registers `campus-customs` as a stdio server (`.venv/Scripts/python.exe mcp_server/server.py`, `CAMPUS_CUSTOMS_DB=data/campus_customs_new.db`). Relative paths resolve against `HW5/`.
- **Test:** `mcp_server/smoke_test.py` starts the server from `.mcp.json` through a FastMCP client, so the tools are called over the real MCP protocol. It calls each tool once and checks the answer against direct read-only SQL. Results are in `output/mcp_smoke.json`.

| Prompt (summary) | Tool | Key output | Verified against DB |
|---|---|---|---|
| Pull everything linked to ticket 101 | `get_ticket_context(101)` | Tee S on hand 0. Invoice 501 is $840 and 3 days overdue. | 6/6 checks pass |
| Ticket 103: 20 hoodies in size M. Stock, vendor, ship status? | `check_stock_and_restock("CC-HOOD-NAVY","M",20)` | 8 on hand, 12 short. Bulldog Print Co, 5 lead days, PO $264, ETA 2026-09-05. Won't ship (invoice 501). | 8/8 checks pass |
| Ticket 102: cash vs. invoices and rent | `get_cash_position()` | $3,400 − $840 − $2,400 = $160 left | 5/5 checks pass |

The three tools are read-only. Since Problem 5, opening the database also creates the workflow tables `approval_requests` and `drafts` in the working copy (never in the original). `reset_db.py` removes them by restoring the original.

## 7. Agent team (`backend/agents.py`, PydanticAI)

| Agent | Prompt file | Responsibilities | MCP tools it can see |
|---|---|---|---|
| **Boss** | `backend/prompts/boss.md` | Reads each ticket, routes it only to the agents it needs, coordinates them, makes final decisions (discounts, priorities, partial fills), sets ticket status. Returns a structured `TicketOutcome`. | `get_open_tickets`, `get_ticket_context`, `update_ticket_status` |
| **Inventory** | `backend/prompts/inventory.md` | Stock by SKU and size, shortages, vendor match, lead time, ETA, ship block. | `get_ticket_context`, `check_stock_and_restock` |
| **Accounting** | `backend/prompts/accounting.md` | Cash, invoices, margins and discounts. Queues payments and purchase orders for human approval, following the priority order. | `get_ticket_context`, `get_cash_position`, `check_stock_and_restock`, `quote_discount`, `request_payment`, `request_purchase_order` |
| **Facilities** | `backend/prompts/facilities.md` | Lease, rent, shop space, landlord drafts. Hands rent payment to Accounting. | `get_ticket_context`, `get_cash_position`, `create_draft` |
| **Customer Service** | `backend/prompts/customer_service.md` | Customer message drafts that only state verified facts. | `get_ticket_context`, `create_draft` |

- **Model:** every agent uses `gpt-6-luna` through Portkey (`https://api.portkey.ai/v1`, key `PORTKEY_API_KEY` loaded from `.env`). `MODEL_NAME` is a constant and deliberately can't be overridden by an environment variable, so no other model can slip in. The agents use PydanticAI's `OpenAIResponsesModel` (the Responses API) because Portkey's `gpt-6-luna` rejects function tools on `/chat/completions`.
- **Full connectivity:** every agent has a `delegate(to, task)` tool that can target any other agent. The child agent shares the parent's usage counter, so the whole ticket is under one budget. Self-delegation is refused.
- **Boss doesn't call everyone:** Boss's prompt routes by ownership (rent goes to Facilities, stock to Inventory, purely financial to Accounting), and specialists pull in others themselves. Example: in the test run of ticket 102, the path was Boss → Facilities → Accounting. Inventory and Customer Service weren't called.
- **Database access only through MCP:** agents have no SQL and no direct database access. One MCP client (launched from `.mcp.json`) is shared by all agents. A per-agent filter shows each agent only its own tools.
- **Entry points:** `agents.run_ticket(ticket_id)`. From the command line: `python backend/run_tickets.py 101` for one ticket, or `python backend/run_tickets.py --all`, which resets the working database first and then runs every open ticket.

## 8. Complete MCP tool list

| Tool | Type | Tables | Tickets | Used by |
|---|---|---|---|---|
| `get_open_tickets()` | read | desk, tickets | all | Boss |
| `get_ticket_context(ticket_id)` | read | desk, tickets, inventory, pricing, invoices, vendors, leases, approval_requests, drafts | 101, 102, 103 | all |
| `check_stock_and_restock(sku, size, qty_needed)` | read | desk, inventory, pricing, vendors, invoices | 101, 103 | Inventory, Accounting |
| `get_cash_position()` | read | desk, cash_accounts, invoices, vendors, leases, payments, approval_requests | 101, 102, 103 | Accounting, Facilities |
| `quote_discount(sku, qty, discount_pct)` | read | pricing | 103 | Accounting |
| `request_payment(ticket_id, kind, ref_id, reason)` | write (queue only) | invoices / leases, cash_accounts, approval_requests | 101 (invoice 501), 102 (rent) | Accounting |
| `request_purchase_order(ticket_id, sku, size, qty, reason)` | write (queue only) | inventory, pricing, vendors, invoices, cash_accounts, approval_requests | 101, 103 | Accounting |
| `create_draft(ticket_id, recipient, recipient_type, subject, body)` | write | drafts | 101, 102, 103 | Customer Service, Facilities |
| `update_ticket_status(ticket_id, status, note)` | write | tickets | 101, 102, 103 | Boss |

**Human-only (not an MCP tool):** `shop_db.decide_approval(request_id, approve, approver)`. Only this function moves money. It is reserved for the dashboard's human approver (a later problem) and no agent can reach it.

### Workflow tables added to the working database
- `approval_requests`: every payment or PO an agent queues (`pending`, then `approved`, `rejected`, or `refused`), with requester, reason, and the decision.
- `drafts`: customer, vendor, and landlord messages with `status = 'draft'`. Nothing is ever sent.

Both are created only in `campus_customs_new.db` and disappear on reset.

## 9. Safety rules: where each is enforced

| Rule | Enforced in code (not just prompts) |
|---|---|
| `desk.date_today` is today | Every date calculation in `shop_db.py` reads `desk`. Prompts forbid using the real calendar. |
| Lead times from `vendors` | Vendor and `lead_days` come from `vendors` (matched on `specialty`). ETA = `date_today + lead_days`. |
| No shipping while an invoice is unpaid | `check_stock_and_restock` reports `vendor_will_ship = false`. `request_purchase_order` marks the PO blocked, and `decide_approval` refuses to approve a PO while the vendor has an open invoice. |
| Human approval for every payment | Agents can only insert `pending` requests. Only `decide_approval` (human, requires an approver name) writes to `payments`, and `payments.approved_by` is NOT NULL. |
| Cash never negative | A request above the current balance is `refused` immediately. Approval runs `UPDATE … WHERE balance >= amount` inside a `BEGIN IMMEDIATE` transaction and refuses if no row is updated. |
| Cash only goes out | No tool adds to cash. `quote_discount` notes that revenue isn't modeled. |
| Drafts only | `create_draft` always stores `status='draft'`. There is no send tool anywhere. |
| Reset before full runs | `run_tickets.py --all` calls `reset_working_db()` first and logs a `database_reset` audit event. |
| Least privilege | Each agent sees only its tools (filtered toolset). A second check at call time denies and audits anything outside `TOOL_ACCESS`. |
| No identity spoofing | The harness overwrites `requested_by`, `author`, and `updated_by` with the calling agent's real name. |
| Amounts come from the database | `request_payment` reads the invoice or rent amount. PO cost = `qty × pricing.unit_cost`. Agents can't type in an amount. |
| No duplicate payments | An existing pending or approved request for the same invoice, lease, or ticket/SKU/size is returned instead of creating a new one. |
| Original database untouched | Tools only open `campus_customs_new.db`. The original is only ever copied from. |

## 10. Audit trail (`output/audit_trail.json`)
`backend/audit.py` appends one JSON event per action and never deletes earlier activity. It reads the existing array, appends, and atomically replaces the file under a lock. A corrupt file is backed up rather than overwritten. Event types:
- `ticket_started`, `ticket_finished`, `ticket_failed`
- `tool_call`, `tool_denied`
- `delegation`, `delegation_result`, `delegation_refused`
- `database_reset`

Each event records the run id, ticket id, agent, a UTC timestamp, and the tool arguments and results (clipped to 2,000 characters per field). `ticket_finished` includes token usage.

## 11. Token and cost controls

| Limit | Value | Where |
|---|---|---|
| Max output tokens per model response | 1,500 | `MODEL_SETTINGS.max_tokens` |
| Model requests per ticket (all agents combined) | 30 | `UsageLimits.request_limit` |
| Tool calls per ticket | 40 | `UsageLimits.tool_calls_limit` |
| Total tokens per ticket | 150,000 | `UsageLimits.total_tokens_limit` |
| Delegation depth | 2 (Boss → specialist → specialist) | `MAX_DELEGATION_DEPTH` |
| Delegations per ticket | 6 | `MAX_DELEGATIONS_PER_TICKET` |
| Parallel tool calls | off | `parallel_tool_calls=False` |
| Model output-validation retries | 2 per agent; MCP tool retries 1 | `Agent(retries=2)`, `MCPToolset(max_retries=1)` |
| Least-privilege tool lists | each agent sees 2–6 of the 9 tools | `TOOL_ACCESS` filter (smaller tool schemas mean fewer input tokens) |
| Audit field clipping | 2,000 chars | `audit.MAX_FIELD_CHARS` |

Child agents share the parent's usage counter, so these limits cap the whole ticket, not each agent separately. **Measured:** the test run of ticket 102 used 12 requests, 9 tool calls, 2 delegations, and 21,727 total tokens (20,462 in, 1,265 out).

## 12. Development test run (Problem 5)
Ticket 102 was run live to verify the wiring. Boss → Facilities → Accounting queued rent request #1 ($2,400, `pending`). Boss set the ticket to `waiting_approval`. No money moved. Two earlier attempts are also in the audit trail:
1. A `ticket_failed` caused by Portkey rejecting tools on `/chat/completions`. Fixed by switching to the Responses API.
2. A run where Boss skipped Facilities and Accounting also queued invoice 501, which is outside the ticket's scope. Fixed by adding routing and "stay within the ticket" rules to the Boss and Accounting prompts.

The working database was reset afterward, so it matches the original again.

## 13. FastAPI backend (`backend/main.py`)

Run from `HW5/` with `.venv/Scripts/python backend/main.py`. It serves `http://127.0.0.1:8000`, with interactive docs at `/docs`. It runs as a single process without the auto-reloader, and CORS is open to the Vite dev server on port 5173.

| Method & route | What it does |
|---|---|
| `GET /api/health` | Liveness check. Also returns the model (`gpt-6-luna`), the working database path, and whether an agent run is in progress. |
| `GET /api/tickets` | All tickets with `status` (`open`, `in_progress`, `waiting_approval`, `blocked`, or `resolved`), `is_resolved`, the number of pending approvals, and the number of drafts. Also returns `date_today`. |
| `GET /api/tickets/{id}` | One ticket with its linked product, invoice, and lease, its approval requests, the full text of its drafts, and the runs that included it. |
| `POST /api/tickets/{id}/run` | Starts the agent team on the selected ticket in the background and returns a `run_id` right away (202). Boss decides which agents work on it. Returns 409 if a run is already going. |
| `POST /api/run-all` | Full run. By default it **resets the working database first**, then runs every open ticket in order (101 → 102 → 103). Body: `{"reset_first": true}`. |
| `GET /api/runs`, `GET /api/runs/{run_id}` | Run status (`queued`, `running`, `finished`, or `failed`), the ticket currently being worked, each ticket's `TicketOutcome`, and any error. |
| `GET /api/activity?limit=&ticket_id=&run_id=&event=` | Recent audit-trail events, newest first: ticket start and finish, agent-to-agent delegations, every MCP tool call with its arguments and result, denied tools, human approval decisions, and resets. |
| `GET /api/drafts?ticket_id=` | Message drafts the agents wrote. They are never sent. |
| `GET /api/approvals?status=pending\|approved\|rejected\|refused\|all` | Payment and purchase-order requests the agents prepared, plus the current balance. |
| `POST /api/approvals/{id}/approve` | **Human approval.** Body: `{"approver": "<name>", "note": ""}`. This is the only route that moves money. It calls `shop_db.decide_approval`, which re-checks the rules at that moment (details below). |
| `POST /api/approvals/{id}/reject` | Human rejects a request. No money moves. |
| `GET /api/cash` | Current **checking balance**, obligations by due date, pending requests, the projected balance if everything pending is approved, and all payments made. |
| `POST /api/reset` | Restores `data/campus_customs_new.db` from the untouched `data/campus_customs.db`. That puts cash back at $3,400, tickets back to open, and removes approvals, drafts, and payments. The audit trail is kept, and a `database_reset` event is appended. Returns 409 during a run. |

### What `POST /api/approvals/{id}/approve` checks and does
- **No money moves without a human.** Agents can only create `pending` requests through MCP. The approve route needs a non-empty `approver` (otherwise 422), and that name is written to `payments.approved_by`.
- **The vendor can't have an unpaid invoice.** A purchase order to a vendor that still has an open invoice returns 409 and stays `pending`, so it can be approved after the invoice is paid.
- **Cash can't go negative.** If the amount is more than the current balance, the request becomes `refused` and no money moves. This is enforced with `UPDATE … WHERE balance >= amount` inside a `BEGIN IMMEDIATE` transaction.
- **A request can only be decided once.** Trying again on an already decided request returns 409, so nothing can be paid twice.
- **What changes on approval:**
  - a `payments` row is added
  - the checking balance goes down
  - the invoice is marked `paid`, or the lease's `next_due` moves forward a month
  - an `approval_approved`, `approval_refused`, or `approval_rejected` event goes to the audit trail
  - a dated note goes on the ticket
- **Approvals pause during runs.** They return 409 while an agent run is in progress, so the cash picture can't change in the middle of a ticket.

### Concurrency
Only one run happens at a time, using an asyncio lock, because runs share one MCP server process and one cash balance. Reset and approvals are blocked while a run is in progress. Run records live in memory, and the audit trail is the durable log.

### Verified (Problem 7)
These checks went through the API against the working database. The database was reset afterward, and all original tables match the original values.

| Check | Result |
|---|---|
| `GET /api/tickets` | 101, 102, and 103 all `open`. |
| `GET /api/cash` | Checking balance $3,400, no payments. |
| PO approved before invoice 501 was paid | 409, "vendor has unpaid invoice(s) [501]". |
| Blank approver | 422. |
| Approve invoice 501, then approve rent | Balance went $3,400 → $2,560 → $160, with payments recorded `approved_by = Alan`. |
| Approve the $264 PO with $160 left | `refused`, balance stayed $160. |
| Approve the same request again | 409. |
| `POST /api/tickets/102/run` | 202. A second run during it got 409. The run finished with Boss → Facilities → Accounting, ticket 102 `waiting_approval`, 1 pending request. |
| `GET /api/activity?run_id=…` | Showed every delegation and MCP call. |
| `POST /api/reset` | Balance back to $3,400, 3 open tickets. |

## 14. React dashboard (`frontend/`)
React 19 + Vite 8 + TypeScript. `npm --prefix frontend run dev` serves http://localhost:5173 and proxies `/api` to FastAPI on port 8000. The design is documented in `output/design.md`. The dashboard has no database access of its own: tickets, cash, approvals, drafts and runs come from the API, and the live agent view is derived from `GET /api/activity` (the audit trail). Approving a payment calls `POST /api/approvals/{id}/approve` with the approver's typed name.

## 15. Clean run: tickets 101, 102, 103 (Problem 9)

### Procedure
1. **Reset:** used the dashboard's **Reset DB** (→ `POST /api/reset`). `campus_customs_new.db` was restored from the untouched original, and a `database_reset` event was logged at `2026-10-14T02:24:00Z`. That event marks the start of the clean run in `audit_trail.json`.
2. **Starting balance:** read from `cash_accounts`: `('checking', 3400.0, '2026-08-31')`. There were no payments, invoice 501 was `open`, and lease 1 was due `2026-09-02`.
3. **Prompt change before the run.** Resolving a ticket takes a second run after the human approves, and Boss had no rule for what "resolved" means once requests are decided. Before any ticket ran, we added a *Follow-up runs* section to `backend/prompts/boss.md`:
   - Never re-queue approved, rejected or refused requests.
   - Make sure the requester's draft reflects the final outcome.
   - Set `resolved` once every approval request is decided and nothing is left for any agent to do. A pending ETA or a declined portion doesn't keep a ticket open.

   The backend was restarted to load it.
4. **Runs:** each ticket was selected on the ticket rail and started with **Run agents**. When requests appeared in the approval tray, the human approved them, signing as *Alan*. The ticket was then run again so Boss could close it.
5. **Approval policy:** approve every request the agents prepared, paying the vendor invoice that blocks shipping first. The register refuses anything unaffordable. No request was rejected, and none hit the cash limit, because the agents themselves declined to queue the unaffordable $264 restock.
6. **Export:** `python backend/export_results.py` builds `output/resolved_tickets.json` from the final database and the clean-run audit events.

### Results

| Ticket | Runs | Agents that worked | Delegations | Human approvals | Cash | Final |
|---|---|---|---|---|---|---|
| 101 Bulldog tee | 2 | Boss, Inventory, Accounting, Customer Service | Boss→Inventory ×2, Inventory→Accounting, Boss→Customer Service ×2 | #1 invoice 501 $840 ✓, #2 PO 1× tee S $8 ✓ (after 501 was paid) | −$848 | resolved |
| 102 Rent due | 2 | Boss, Facilities, Accounting | Boss→Facilities ×2, Facilities→Accounting | #3 rent $2,400 ✓ | −$2,400 | resolved |
| 103 Bulk hoodies | 1 | Boss, Inventory, Accounting, Customer Service | Boss→Inventory, Inventory→Accounting, Boss→Accounting, Boss→Customer Service | none. The $264 restock was more than the $152 in checking, so it wasn't queued | $0 | resolved |

**Cash:** $3,400.00 → $2,560.00 (invoice 501) → $2,552.00 (tee PO) → **$152.00** (rent). The final balance equals `cash_accounts.checking = 152.0`.

**Drafts:** 5 in total, all `status='draft'` and never sent:
- 101: #1 and #2 to Tauhid Zaman
- 102: #3 and #4 to Elm City Properties
- 103: #5 to the Yale AI Club

**Ticket 103 decision:** 5% off the 8 hoodies in stock ($55.10 each, $440.80), with no commitment on the other 12.

**Agents that weren't needed:**
- Facilities on 101 and 103.
- Inventory and Customer Service on 102.

So Boss never called all five agents.

**Tokens:** 101 used 59,186, 102 used 35,604 and 103 used 52,777, for a total of **147,567** across 5 runs. Every run was inside the per-ticket limits (max 34,903 per run vs the 150,000 limit).

### Rule verification (computed in `resolved_tickets.json` → `rule_checks`, all `true`)

| Rule | Evidence |
|---|---|
| `desk.date_today` is today | Invoice 501 was treated as 3 days overdue (due 08-28 vs 08-31). Rent was "due in 2 days" and not overdue. All dates are 2026-08-31 based. |
| Lead times from `vendors` | Bulldog Print Co `lead_days = 5` gave an ETA of 2026-09-05 for 101 and 103. |
| No shipping with an unpaid invoice | The PO for 101 was marked blocked by invoice 501 and approved only after 501 was paid (payment #1 before #2). |
| Human approval for every payment | All 3 `payments` rows have `approved_by = 'Alan'`, and each matches an approved `approval_requests` row. Agents only created `pending` requests. |
| Refuse if not enough cash / never negative | The $264 restock (> $152) wasn't queued, and the register would have refused it. The lowest balance was $152. |
| Cash only goes out | Three debits, no credits. The 103 sale adds no cash. |
| No real emails or vendor contact | No send tool exists. All 5 messages are drafts on the board. |
| Only `gpt-6-luna` | Every `ticket_started` event in the clean run records `model: gpt-6-luna`. |
| Original database untouched | `campus_customs.db` SHA-256 is still `23686a90…f360a`. |

### Output files
- `output/desk_tickets.html`: the Actual sections (agents, delegations, MCP tools, expected vs. actual) and the Cash tab. Expected sections are kept.
- `output/resolved_tickets.json`: final status, decision, runs, delegations, tool calls, approvals, payments, drafts and cash for each ticket, plus the rule checks.
- `output/resolved_board.html`: dashboard screenshots after each ticket was resolved. The images are embedded, and the originals are in `output/screenshots/`.
- `output/audit_trail.json`: every clean-run event was appended after the `database_reset` at 02:24:00Z, and earlier activity was kept.
