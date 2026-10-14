# Campus Customs MCP Server

A [FastMCP](https://gofastmcp.com) server that gives the Campus Customs agent team (Boss, Inventory, Accounting, Facilities, Customer Service) structured access to the shop's database. The agents have no SQL access. Every fact they use and every change they make goes through these tools, which enforce the shop rules in code.

## Files
| File | Purpose |
|---|---|
| `server.py` | Exposes the MCP tools (stdio transport). |
| `shop_db.py` | All database logic and rule enforcement, shared with the backend. |
| `smoke_test.py` | Calls the tools over the real MCP protocol and checks the results against SQL. Writes `output/mcp_smoke.json`. |

## Database
- **Uses:** `data/campus_customs_new.db`, the working copy. You can override the path with `CAMPUS_CUSTOMS_DB`; relative paths resolve against `HW5/`.
- **Never touches:** `data/campus_customs.db`, the original. Run `python reset_db.py` from `HW5/` to restore the working copy, which you must do before every full run.
- **Shop date:** every date calculation uses `desk.date_today` (`2026-08-31`), not the computer's clock.
- **Workflow tables:** two tables are created in the working copy only and disappear on reset:
  - `approval_requests`: payments and POs waiting for a human.
  - `drafts`: messages that are never sent.

## Complete tool list (9)

### Read tools
| Tool | What it returns | Tickets |
|---|---|---|
| `get_open_tickets()` | Every unresolved ticket (id, type, requester, subject, status) plus `date_today`. | all |
| `get_ticket_context(ticket_id)` | The ticket plus everything linked to it: product stock (requested size and all sizes), price, cost, margin, linked invoice (days overdue), linked lease (days until due), and any approval requests and drafts already made for the ticket. | 101, 102, 103 |
| `check_stock_and_restock(sku, size, qty_needed)` | On hand, can fill now, and shortage. For a shortage it also gives the vendor picked from `vendors.specialty`, `lead_days`, PO cost (`shortage × unit_cost`), ETA (`date_today + lead_days`), and `vendor_will_ship = false` plus the blocking invoices if the vendor has an open unpaid invoice. | 101, 103 |
| `get_cash_position()` | Checking balance and open invoices plus rent, sorted by due date, with overdue flags. Also gives the running balance if paid in order, pending approval requests, and recent payments. | 101, 102, 103 |
| `quote_discount(sku, qty, discount_pct)` | Discounted unit price, order totals, customer savings, margin after discount, a `sells_below_cost` flag, and the maximum discount without a loss. | 103 |

### Write tools (agents can only queue; they can't pay)
| Tool | What it does | Tickets |
|---|---|---|
| `request_payment(ticket_id, kind, ref_id, requested_by, reason)` | Queues an `invoice` or `rent` payment as a **pending** approval request. The amount is read from the database. The request is refused immediately if the amount exceeds cash. Duplicates aren't created. | 101 (invoice 501), 102 (rent) |
| `request_purchase_order(ticket_id, sku, size, qty, requested_by, reason)` | Queues a restock PO (`qty × unit_cost`) to the matching vendor. It's refused if over cash, and marked **blocked** if the vendor has an unpaid invoice. | 101, 103 |
| `create_draft(ticket_id, recipient, recipient_type, subject, body, author)` | Saves a customer, vendor, or landlord message with `status='draft'`. **Nothing is ever sent.** | 101, 102, 103 |
| `update_ticket_status(ticket_id, status, note, updated_by)` | Sets the status (`open`, `in_progress`, `waiting_approval`, `blocked`, or `resolved`) and appends a dated note. Earlier notes are kept. | 101, 102, 103 |

The backend overwrites `requested_by`, `author`, and `updated_by` with the calling agent's real name.

### Human-only function (deliberately not an MCP tool)
`shop_db.decide_approval(request_id, approve, approver, note)` is the only code path that moves money. It re-checks the rules at approval time:
- A PO can't be approved while its vendor has an open invoice.
- The cash update is `UPDATE … WHERE balance >= amount` inside a transaction, so a payment that would make cash negative is **refused**.

On approval it writes `payments` (with `approved_by`), marks the invoice `paid` or rolls the lease's `next_due` forward a month, and lowers the cash balance. No agent can call it. It's for the dashboard's human approver.

## Shop rules built into the tools
- `desk.date_today` is "today".
- Vendors and lead times come only from the `vendors` table.
- A vendor with an open unpaid invoice won't ship.
- Every payment needs human approval.
- Cash can never go negative.
- Cash only goes out; revenue isn't modeled.
- Messages are drafts only.

## Connect and test
`HW5/.mcp.json` registers the server as `campus-customs` (stdio, `.venv/Scripts/python.exe mcp_server/server.py`). Claude Code picks it up when started from `HW5/`, and the agent backend (`backend/agents.py`) launches it from the same config.

```bash
cd HW5
.venv/Scripts/python mcp_server/smoke_test.py
```
