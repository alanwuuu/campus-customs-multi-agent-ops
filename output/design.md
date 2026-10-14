# Campus Customs Ops Desk: design notes

The dashboard (`frontend/`, React + Vite + TypeScript) is meant to feel like the back counter of the Chapel Street shop: tickets come in on a rail, five agents work at their stations, money sits in a register, and anything that spends cash waits in a tray for a human signature. Every screen element maps to something real in the backend (FastAPI `backend/main.py`), so what you see is what the agents actually did.

Run it with the backend on port 8000 (`.venv/Scripts/python backend/main.py`), then `npm run dev` in `frontend/` and open `http://localhost:5173`. Vite proxies `/api` to FastAPI.

## 1. Overall concept and layout

| Zone | Shop metaphor | What it shows |
|---|---|---|
| Top bar | The desk header | Brand, **desk date** (`desk.date_today`, not the real date), model (`gpt-6-luna`), team status (idle / agents on #N / backend offline), approvals waiting, **Reset DB** and **Full run** |
| Left: **Ticket rail** | Paper order tickets clipped to a rail | Tickets 101–103 with open/resolved state, workflow stamp, pending approvals and drafts |
| Center top: **Ticket bar** | The ticket currently in your hand | Big ticket number, subject, requester, the original note, status stamp, and the **Run agents** button |
| Center: **Agent stations** | Five workstations along the counter | What each agent is doing right now |
| Center: **Hand-off map** and **Shift report** | Whiteboard and end-of-shift notes | Who delegated to whom, Boss's final decision, and a summary card for each agent |
| Center bottom: **Live wire** | The radio chatter | Every event in order: delegations, MCP tool calls with arguments and results, approvals |
| Right: **Register** | The cash register | Checking balance (animated), money waiting on you, projected balance, bills due |
| Right: **Approval tray** | Receipts waiting for a signature | Payments and purchase orders the agents prepared, with Approve & pay / Reject |
| Right: **Outbox** | Unsent letters | Drafts the agents wrote, each stamped **NOT SENT** |

The three-column layout puts the work (tickets → agents → money) in reading order from left to right. Below 1,360px the right column moves under the main area. Below 980px everything stacks, the ticket rail scrolls sideways, and the stations wrap two-up, then one-up on phones.

## 2. Visual style
- **Black and pink.** This is the workspace's house style for web apps. The near-black counter (`#0a0a0c`) with a faint ledger-line grid keeps the busy data readable. Hot pink (`#ff4fa3`) is reserved for the brand, the selected ticket, primary actions, and "something is happening now" (live dots, glows).
- **Physical objects instead of generic cards.** Tickets have a perforated stub. Statuses are tilted rubber stamps (OPEN, NEEDS APPROVAL, BLOCKED, RESOLVED). The balance sits on a glowing register LCD in monospace digits. Approval requests are cream paper receipts with a torn bottom edge, so they look like something you sign, and they stand out against the dark UI exactly where a human has to act. Drafts carry a NOT SENT stamp.
- **Typography.** The system UI font for text, monospace for money, ticket numbers, SKUs, timestamps and tool names, so you can tell at a glance what's data and what's prose. Section labels are small uppercase pink headings.
- **Motion with a purpose:** the working agent's avatar bobs and its station glows, live dots pulse, new feed lines slide in, and the register counts down and flashes when money leaves. Everything respects `prefers-reduced-motion`.

## 3. Telling the five agents apart
Each agent has a **color, a glyph, a full name and a two-letter call sign**, so they're distinguishable by shape and text, not only by hue:

| Agent | Color | Glyph | Call sign |
|---|---|---|---|
| Boss | Pink `#ff4fa3` (the brand color, because Boss runs the desk) | Crown | BS |
| Inventory | Cyan `#4cc9f0` | Shipping box | IN |
| Accounting | Gold `#ffc857` | Coin with $ | AC |
| Facilities | Green `#7ae582` | Storefront | FA |
| Customer Service | Violet `#b79cff` | Speech bubble | CS |

The same identity is used everywhere: the station's top border and avatar, map nodes and arrow colors (an arrow takes the color of the agent who delegated), summary card borders, feed badges, "prepared by" on approval slips, and draft authors. The human approver gets a distinct white **You** badge so human actions never look like agent actions. All glyphs are inline SVG in `src/agents.tsx`; no image assets are used.

## 4. How agent activity is shown
The backend writes every step to `output/audit_trail.json`. The dashboard polls `GET /api/activity?ticket_id=…` (every 1.2s while a run is going, every 5s when the desk is idle) and derives everything from that one source in `src/derive.ts`:

- **Agent stations (live state).** The run is replayed as a call stack. `ticket_started` puts Boss on the stack. Each `delegation` pushes the receiving agent, and each `delegation_result` pops it. The agent on top is **Working** (glowing, bobbing avatar). The agents under it are **Waiting** on the one they handed off to. Agents that reported back are **Done**. Agents never involved stay dimmed as **Idle**. Each station shows a plain-English line ("From Inventory: Ticket 101 restock…", "Waiting on Accounting", "Reported to Boss") and the last MCP tool it used.
- **Hand-off map (delegations).** The five agents sit on a pentagon with Boss at the top. Each delegation is a curved arrow in the delegating agent's color. A numbered disc gives the order it first happened, and the arrow gets thicker with repeats. Agents that didn't take part fade out. This makes the key design goal visible: **Boss does not call everyone.** For ticket 101 the map shows Boss → Inventory → Accounting and Boss → Customer Service, with Facilities greyed out.
- **Live wire (tool use).** It's a reverse-chronological feed. Each MCP call is shown as `get_cash_position()` or `check_stock_and_restock("CC-TEE-WHITE", "S", 1)`, and you can expand it to see the full arguments and the result the tool returned. Delegations show the actual task text, and reports show the full reply. Denied tools, refused hand-offs and failures are tinted red, and the finished run is tinted green.
- **Shift report (what each agent did).** Boss's final decision comes first: its status stamp, the decision, and its list of actions. Then there's one card for each agent that took part, showing who called it, who it handed off to, each MCP tool with a count, and its written report (expandable). It ends with "Not needed for this ticket" and the agents that were skipped. The header shows the run's model calls, tool calls and total tokens, which ties into our token limits.
- **Following a run.** **Run agents** starts the selected ticket. **Full run** resets the database and runs 101 → 102 → 103, and the dashboard automatically follows whichever ticket the agents are on. Toasts announce start, finish and failure. If a run is older than the latest database reset, the shift report says so, so a stale result is never mistaken for the current one.

## 5. How ticket status is shown
- **Open vs. resolved** is the first thing on every ticket card (● OPEN in pink, ✓ RESOLVED in green), and the rail header counts both. That's the binary state the assignment asks for.
- **The workflow stamp** gives the finer state Boss recorded: Open, In progress, **Needs approval** (amber), **Blocked** (red), Resolved (green). The same stamp appears on the ticket bar and in Boss's final decision.
- **Small chips** on each ticket show how many approvals are waiting and how many drafts exist. While agents work on a ticket, its card glows and shows "agents working".

## 6. How cash and approvals are shown
- **Register.** The checking balance from `GET /api/cash` is shown on an LCD. Below it:
  - **Waiting on you:** the total of pending requests.
  - **If all approved:** the projected balance. It turns red, with a warning, if approving everything would overdraw checking.
  - The last payment, with who approved it.
  - A collapsible list of bills: open invoices and rent, with days overdue or days until due, counted from the desk date.
- **The balance updates after approval.** Approving a payment calls `POST /api/approvals/{id}/approve`, then refreshes immediately. The register counts down from the old balance to the new one and flashes pink, so you can see the money leave. In testing, approving invoice 501 moved it $3,400 → $2,560, then the $8 PO moved it to $2,552.
- **Approval tray.** Each slip shows the kind (vendor invoice, rent, purchase order), the amount, the payee, the ticket, the agent's reason, and which agent prepared it. Flags warn **before** you click:
  - "Vendor blocked until invoice 501 is paid." This is checked live against the invoices that are still open.
  - "More than the $X in checking. It will be refused."
- **The human signs.** You have to type your name in **Signing as** (remembered in this browser), and the buttons stay disabled until you do. That name becomes `payments.approved_by`.
- **The backend has the final say.** It refuses overdrafts and blocks POs to vendors with unpaid invoices, and the response appears as a toast ("Cannot approve yet: vendor has unpaid invoice(s) [501]", "Refused: … Cash can never go negative"). Approvals are locked while agents are running. A "Recently decided" list keeps approved, refused and rejected stamps visible.

## 7. Why we designed it this way
1. **Make multi-agent behavior inspectable, not magical.** The point of the assignment is the team's routing and delegation. The stations, the map and the feed show the same run at three zoom levels (now, structure, detail), so a grader or shop manager can check that Boss involved only the agents a ticket needed and that every fact came from an MCP tool.
2. **Put the human exactly where money moves.** Payments are the only irreversible action, so they get the strongest visual treatment: paper slips with warnings and a required signature. The dashboard never implies money moved until the backend confirms it, and then the register visibly changes.
3. **Make the shop rules visible.** The desk date sits in the header, vendor blocks and overdraft risk are flagged on slips, the register projects the balance after pending approvals, and drafts are stamped NOT SENT. Each rule from the harness appears somewhere on screen.
4. **One source of truth.** Everything is derived from the audit trail and the working database through the API. Nothing is simulated in the browser, so the dashboard can't drift from what the agents did.
5. **Accessible and robust:**
   - Agents are identified by glyph and text, not just color.
   - Keyboard focus rings are pink.
   - The feed uses `aria-live`, and reduced-motion is respected.
   - Layouts are responsive down to phone width.
   - An offline banner tells you how to start the backend.
   - The register shows the right balance even if the tab was in the background during an update.
