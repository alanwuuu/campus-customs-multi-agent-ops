"""Campus Customs database logic shared by the MCP server and (later) the FastAPI backend.

Everything works on the working database `data/campus_customs_new.db`.
All dates come from `desk.date_today`, never the real clock.

Shop rules enforced here (not just in prompts):
  - vendors with an open unpaid invoice will not ship (purchase orders blocked)
  - agents can only *request* payments; `decide_approval` is the human-only step
  - a payment larger than the cash balance is refused; cash never goes negative
  - cash only goes out
  - messages are stored as drafts and never sent
"""
from __future__ import annotations

import calendar
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

HW5_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("CAMPUS_CUSTOMS_DB", "data/campus_customs_new.db"))
if not DB_PATH.is_absolute():
    DB_PATH = HW5_DIR / DB_PATH  # relative paths are relative to HW5/, whatever the launch cwd

CASH_ACCOUNT = "checking"

# Product line -> keyword in vendors.specialty. Vendor choice and lead time
# still come from the vendors table; this only says what kind of supplier a SKU needs.
SKU_CATEGORY = {
    "CC-HOOD": "apparel",
    "CC-TEE": "apparel",
    "CC-HAT": "apparel",
    "CC-MUG": "mugs",
}

TICKET_STATUSES = ("open", "in_progress", "waiting_approval", "blocked", "resolved")
RECIPIENT_TYPES = ("customer", "vendor", "landlord", "other")

# Tables our agent workflow adds to the *working* copy only. reset_db.py drops
# them by copying the original back; they are recreated on first use.
_EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    kind TEXT NOT NULL,            -- invoice | rent | purchase_order
    ref_id INTEGER,                -- invoice id / lease id / NULL for POs
    vendor_id INTEGER,
    payee TEXT NOT NULL,
    amount REAL NOT NULL,
    details TEXT,                  -- JSON
    status TEXT NOT NULL,          -- pending | approved | rejected | refused
    requested_by TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,      -- shop date
    decided_by TEXT,
    decided_at TEXT,
    decision_note TEXT,
    payment_id INTEGER
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    recipient TEXT NOT NULL,
    recipient_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',   -- always 'draft': nothing is ever sent
    created_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------- helpers

def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found: {DB_PATH}. Run reset_db.py first.")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_EXTRA_SCHEMA)
    return conn


def today(conn: sqlite3.Connection) -> date:
    return date.fromisoformat(conn.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def cash_balance(conn: sqlite3.Connection) -> float:
    row = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (CASH_ACCOUNT,)).fetchone()
    return float(row["balance"]) if row else 0.0


def add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def open_invoices(conn: sqlite3.Connection, now: date, vendor_id: int | None = None) -> list[dict]:
    sql = """SELECT i.id, i.vendor_id, v.name AS vendor, i.amount, i.due_date, i.status, i.description
             FROM invoices i JOIN vendors v ON v.id = i.vendor_id
             WHERE i.status = 'open'"""
    params: tuple = ()
    if vendor_id is not None:
        sql += " AND i.vendor_id = ?"
        params = (vendor_id,)
    rows = []
    for r in conn.execute(sql + " ORDER BY i.due_date", params):
        days = (date.fromisoformat(r["due_date"]) - now).days
        rows.append({**dict(r), "days_until_due": days, "overdue": days < 0,
                     "days_overdue": max(0, -days)})
    return rows


def pricing(conn: sqlite3.Connection, sku: str) -> dict | None:
    r = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if r is None:
        return None
    margin = r["list_price"] - r["unit_cost"]
    return {"unit_cost": r["unit_cost"], "list_price": r["list_price"],
            "unit_margin": round(margin, 2),
            "margin_pct": round(100 * margin / r["list_price"], 1)}


def vendor_for_sku(conn: sqlite3.Connection, sku: str) -> sqlite3.Row | None:
    category = next((c for prefix, c in SKU_CATEGORY.items() if sku.startswith(prefix)), None)
    if category is None:
        return None
    return conn.execute(
        "SELECT id, name, specialty, lead_days FROM vendors WHERE specialty LIKE ? ORDER BY lead_days",
        (f"%{category}%",)).fetchone()


def _approval_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["details"] = json.loads(d["details"]) if d.get("details") else None
    return d


def pending_approvals(conn: sqlite3.Connection) -> list[dict]:
    return [_approval_dict(r) for r in
            conn.execute("SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY id")]


# ---------------------------------------------------------------- read operations

def get_open_tickets() -> dict:
    with closing(connect()) as conn:
        rows = conn.execute("SELECT id, type, requester, subject, status, created_at FROM tickets "
                            "WHERE status != 'resolved' ORDER BY created_at").fetchall()
        return {"date_today": today(conn).isoformat(), "tickets": [dict(r) for r in rows]}


def get_ticket_context(ticket_id: int) -> dict:
    with closing(connect()) as conn:
        now = today(conn)
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"Ticket {ticket_id} not found"}
        ctx: dict = {"date_today": now.isoformat(), "ticket": dict(t)}

        if t["sku"]:
            stock = conn.execute("SELECT name, size, qty, location FROM inventory WHERE sku = ? ORDER BY rowid",
                                 (t["sku"],)).fetchall()
            in_size = next((s for s in stock if s["size"] == t["size"]), None)
            ctx["product"] = {
                "sku": t["sku"],
                "name": stock[0]["name"] if stock else None,
                "requested_size": t["size"],
                "requested_qty": t["qty"],
                "on_hand_in_size": in_size["qty"] if in_size else 0,
                "stock_all_sizes": {s["size"]: s["qty"] for s in stock},
                "pricing": pricing(conn, t["sku"]),
            }

        if t["invoice_id"]:
            inv = next((i for i in open_invoices(conn, now) if i["id"] == t["invoice_id"]), None)
            if inv is None:
                row = conn.execute("SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],)).fetchone()
                inv = dict(row) if row else {"error": f"Invoice {t['invoice_id']} not found"}
            ctx["invoice"] = inv

        if t["lease_id"]:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            if lease:
                days = (date.fromisoformat(lease["next_due"]) - now).days
                ctx["lease"] = {**dict(lease), "days_until_due": days, "overdue": days < 0}

        ctx["approval_requests"] = [_approval_dict(r) for r in conn.execute(
            "SELECT * FROM approval_requests WHERE ticket_id = ? ORDER BY id", (ticket_id,))]
        ctx["drafts"] = [dict(r) for r in conn.execute(
            "SELECT id, recipient, recipient_type, subject, author, status FROM drafts WHERE ticket_id = ?",
            (ticket_id,))]
        return ctx


def check_stock_and_restock(sku: str, size: str, qty_needed: int) -> dict:
    with closing(connect()) as conn:
        now = today(conn)
        row = conn.execute("SELECT name, qty, location FROM inventory WHERE sku = ? AND size = ?",
                           (sku, size)).fetchone()
        if row is None:
            return {"error": f"No inventory row for sku={sku} size={size}"}

        on_hand = row["qty"]
        shortage = max(0, qty_needed - on_hand)
        price = pricing(conn, sku)
        result: dict = {
            "date_today": now.isoformat(),
            "sku": sku, "name": row["name"], "size": size, "location": row["location"],
            "qty_needed": qty_needed, "on_hand": on_hand,
            "can_fill_now": min(on_hand, qty_needed), "shortage": shortage,
            "pricing": price,
        }
        if shortage == 0:
            result["restock"] = None
            return result

        vendor = vendor_for_sku(conn, sku)
        if vendor is None:
            result["restock"] = {"error": f"No vendor in vendors table supplies {sku}"}
            return result

        blocking = open_invoices(conn, now, vendor["id"])
        result["restock"] = {
            "vendor_id": vendor["id"], "vendor": vendor["name"], "specialty": vendor["specialty"],
            "lead_days": vendor["lead_days"],
            "po_qty": shortage,
            "po_cost": round(shortage * price["unit_cost"], 2) if price else None,
            "vendor_will_ship": not blocking,
            "blocking_invoices": blocking,
            "eta_if_ordered_today": (now + timedelta(days=vendor["lead_days"])).isoformat(),
            "note": ("Vendor has an open unpaid invoice and will not ship until it is paid "
                     "(payment needs human approval)." if blocking else "Vendor can ship."),
        }
        return result


def get_cash_position() -> dict:
    with closing(connect()) as conn:
        now = today(conn)
        accounts = [dict(r) for r in conn.execute("SELECT name, balance, date FROM cash_accounts")]
        balance = sum(a["balance"] for a in accounts)

        obligations = [
            {"kind": "invoice", "ref_id": i["id"], "payee": i["vendor"], "amount": i["amount"],
             "due_date": i["due_date"], "days_until_due": i["days_until_due"],
             "overdue": i["overdue"], "description": i["description"]}
            for i in open_invoices(conn, now)
        ]
        for lease in conn.execute("SELECT * FROM leases"):
            days = (date.fromisoformat(lease["next_due"]) - now).days
            obligations.append({"kind": "rent", "ref_id": lease["id"], "payee": lease["landlord"],
                                "amount": lease["monthly_rent"], "due_date": lease["next_due"],
                                "days_until_due": days, "overdue": days < 0,
                                "description": f"Rent for {lease['space_name']}"})
        obligations.sort(key=lambda o: o["due_date"])

        running = balance
        for o in obligations:
            running = round(running - o["amount"], 2)
            o["balance_after_if_paid"] = running
            o["affordable_in_order"] = running >= 0

        total = round(sum(o["amount"] for o in obligations), 2)
        pending = pending_approvals(conn)
        pending_total = round(sum(p["amount"] for p in pending), 2)
        recent = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY id DESC LIMIT 5")]
        return {
            "date_today": now.isoformat(),
            "accounts": accounts,
            "cash_balance": balance,
            "obligations": obligations,
            "total_obligations": total,
            "balance_after_all_obligations": round(balance - total, 2),
            "pending_approval_requests": pending,
            "balance_if_all_pending_approved": round(balance - pending_total, 2),
            "recent_payments": recent,
            "rules": ["Every payment needs human approval.",
                      "Refuse any payment larger than the current balance; cash never goes negative.",
                      "No revenue is modeled; cash only goes out."],
        }


def quote_discount(sku: str, qty: int, discount_pct: float) -> dict:
    if not 0 <= discount_pct < 100:
        return {"error": "discount_pct must be between 0 and 100"}
    with closing(connect()) as conn:
        price = pricing(conn, sku)
        if price is None:
            return {"error": f"No pricing for {sku}"}
        unit = round(price["list_price"] * (1 - discount_pct / 100), 2)
        unit_margin = round(unit - price["unit_cost"], 2)
        return {
            "sku": sku, "qty": qty, "discount_pct": discount_pct,
            "list_price": price["list_price"], "unit_cost": price["unit_cost"],
            "discounted_unit_price": unit,
            "order_total_at_list": round(price["list_price"] * qty, 2),
            "order_total_discounted": round(unit * qty, 2),
            "customer_savings": round((price["list_price"] - unit) * qty, 2),
            "unit_margin": unit_margin,
            "margin_pct": round(100 * unit_margin / unit, 1) if unit else None,
            "order_margin": round(unit_margin * qty, 2),
            "sells_below_cost": unit_margin < 0,
            "max_discount_pct_without_loss": round(100 * price["unit_margin"] / price["list_price"], 1),
            "note": "Revenue is not modeled: a sale does not add to the cash balance in this assignment.",
        }


# ---------------------------------------------------------------- write operations (agents)

def _existing_request(conn, kind: str, ref_id: int | None, details_key: str | None = None) -> dict | None:
    rows = conn.execute("SELECT * FROM approval_requests WHERE kind = ? AND status IN ('pending','approved') "
                        "AND ((ref_id IS NULL AND ? IS NULL) OR ref_id = ?) ORDER BY id",
                        (kind, ref_id, ref_id)).fetchall()
    for r in rows:
        if details_key is None or (r["details"] and json.loads(r["details"]).get("key") == details_key):
            return _approval_dict(r)
    return None


def _insert_request(conn, *, ticket_id, kind, ref_id, vendor_id, payee, amount, details,
                    requested_by, reason) -> dict:
    now = today(conn)
    balance = cash_balance(conn)
    pending_total = sum(p["amount"] for p in pending_approvals(conn))
    if amount > balance:
        status = "refused"
        verdict = (f"REFUSED: ${amount:,.2f} exceeds the cash balance of ${balance:,.2f}. "
                   "Cash can never go negative.")
    else:
        status = "pending"
        verdict = "Queued for human approval on the dashboard. No money has moved."
        if balance - pending_total - amount < 0:
            verdict += (f" WARNING: together with ${pending_total:,.2f} already pending, approving everything "
                        f"would exceed the ${balance:,.2f} balance; the human must choose, and any approval "
                        "that would overdraw cash will be refused.")
    cur = conn.execute(
        """INSERT INTO approval_requests (ticket_id, kind, ref_id, vendor_id, payee, amount, details, status,
                                          requested_by, reason, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (ticket_id, kind, ref_id, vendor_id, payee, round(amount, 2), json.dumps(details), status,
         requested_by, reason, now.isoformat()))
    conn.commit()
    req = _approval_dict(conn.execute("SELECT * FROM approval_requests WHERE id = ?", (cur.lastrowid,)).fetchone())
    return {"request": req, "cash_balance": balance, "result": verdict}


def request_payment(ticket_id: int, kind: str, ref_id: int, requested_by: str, reason: str) -> dict:
    """Queue an invoice or rent payment for human approval. Amount comes from the DB."""
    with closing(connect()) as conn:
        if kind == "invoice":
            inv = conn.execute("SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id = i.vendor_id "
                               "WHERE i.id = ?", (ref_id,)).fetchone()
            if inv is None:
                return {"error": f"Invoice {ref_id} not found"}
            if inv["status"] != "open":
                return {"error": f"Invoice {ref_id} is already {inv['status']}"}
            payee, amount, vendor_id = inv["vendor"], inv["amount"], inv["vendor_id"]
            details = {"invoice_due_date": inv["due_date"], "description": inv["description"]}
        elif kind == "rent":
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return {"error": f"Lease {ref_id} not found"}
            payee, amount, vendor_id = lease["landlord"], lease["monthly_rent"], None
            details = {"space_name": lease["space_name"], "rent_due_date": lease["next_due"]}
        else:
            return {"error": "kind must be 'invoice' or 'rent' (use request_purchase_order for restocks)"}

        existing = _existing_request(conn, kind, ref_id)
        if existing:
            return {"request": existing, "result": "A request for this payment already exists; not duplicated."}
        return _insert_request(conn, ticket_id=ticket_id, kind=kind, ref_id=ref_id, vendor_id=vendor_id,
                               payee=payee, amount=amount, details=details,
                               requested_by=requested_by, reason=reason)


def request_purchase_order(ticket_id: int, sku: str, size: str, qty: int, requested_by: str, reason: str) -> dict:
    """Queue a restock purchase order for human approval. Cost = qty x unit_cost."""
    if qty <= 0:
        return {"error": "qty must be positive"}
    with closing(connect()) as conn:
        now = today(conn)
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return {"error": f"No inventory row for sku={sku} size={size}"}
        price = pricing(conn, sku)
        vendor = vendor_for_sku(conn, sku)
        if price is None or vendor is None:
            return {"error": f"No pricing or vendor for {sku}"}
        key = f"{ticket_id}:{sku}:{size}"
        existing = _existing_request(conn, "purchase_order", None, key)
        if existing:
            return {"request": existing, "result": "A purchase order for this ticket/SKU/size already exists."}
        blocking = open_invoices(conn, now, vendor["id"])
        details = {"key": key, "sku": sku, "size": size, "qty": qty, "unit_cost": price["unit_cost"],
                   "lead_days": vendor["lead_days"],
                   "eta_if_approved_today": (now + timedelta(days=vendor["lead_days"])).isoformat(),
                   "blocked_by_open_invoices": [i["id"] for i in blocking]}
        out = _insert_request(conn, ticket_id=ticket_id, kind="purchase_order", ref_id=None,
                              vendor_id=vendor["id"], payee=vendor["name"], amount=qty * price["unit_cost"],
                              details=details, requested_by=requested_by, reason=reason)
        if blocking and out["request"]["status"] == "pending":
            out["result"] += (f" BLOCKED: {vendor['name']} will not ship while invoice(s) "
                              f"{[i['id'] for i in blocking]} are unpaid; this PO cannot be approved until they are paid.")
        return out


def create_draft(ticket_id: int, recipient: str, recipient_type: str, subject: str, body: str, author: str) -> dict:
    if recipient_type not in RECIPIENT_TYPES:
        return {"error": f"recipient_type must be one of {RECIPIENT_TYPES}"}
    with closing(connect()) as conn:
        cur = conn.execute(
            "INSERT INTO drafts (ticket_id, recipient, recipient_type, subject, body, author, status, created_at) "
            "VALUES (?,?,?,?,?,?, 'draft', ?)",
            (ticket_id, recipient, recipient_type, subject, body, author, today(conn).isoformat()))
        conn.commit()
        return {"draft_id": cur.lastrowid, "status": "draft",
                "result": "Saved as a draft on the board. It has NOT been sent to anyone."}


def update_ticket_status(ticket_id: int, status: str, note: str, updated_by: str) -> dict:
    if status not in TICKET_STATUSES:
        return {"error": f"status must be one of {TICKET_STATUSES}"}
    with closing(connect()) as conn:
        t = conn.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"error": f"Ticket {ticket_id} not found"}
        stamp = f"[{today(conn).isoformat()} {updated_by} -> {status}] {note}"
        notes = f"{t['notes']}\n{stamp}" if t["notes"] else stamp
        conn.execute("UPDATE tickets SET status = ?, notes = ? WHERE id = ?", (status, notes, ticket_id))
        conn.commit()
        return {"ticket_id": ticket_id, "status": status, "note_added": stamp}


# ---------------------------------------------------------------- human-only operation

def decide_approval(request_id: int, approve: bool, approver: str, note: str = "") -> dict:
    """Human decision on a queued request. NOT exposed to agents.

    Approving re-checks every rule at the moment money would move: the vendor must
    not be blocked (POs) and the amount must not exceed the current cash balance.
    """
    if not approver or not approver.strip():
        return {"error": "approver name is required"}
    with closing(connect()) as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            r = conn.execute("SELECT * FROM approval_requests WHERE id = ?", (request_id,)).fetchone()
            if r is None:
                raise ValueError(f"Request {request_id} not found")
            if r["status"] != "pending":
                raise ValueError(f"Request {request_id} is already {r['status']}")
            now = today(conn).isoformat()

            def finish(status: str, msg: str, payment_id: int | None = None) -> dict:
                conn.execute("UPDATE approval_requests SET status=?, decided_by=?, decided_at=?, decision_note=?, "
                             "payment_id=? WHERE id=?", (status, approver, now, note or msg, payment_id, request_id))
                conn.execute("COMMIT")
                return {"request_id": request_id, "status": status, "result": msg,
                        "cash_balance": cash_balance(conn), "payment_id": payment_id}

            if not approve:
                return finish("rejected", "Rejected by human. No money moved.")

            if r["kind"] == "purchase_order":
                blocking = open_invoices(conn, today(conn), r["vendor_id"])
                if blocking:
                    conn.execute("ROLLBACK")
                    return {"request_id": request_id, "status": "pending",
                            "error": f"Cannot approve yet: vendor has unpaid invoice(s) {[i['id'] for i in blocking]}."}

            amount = float(r["amount"])
            cur = conn.execute("UPDATE cash_accounts SET balance = ROUND(balance - ?, 2), date = ? "
                               "WHERE name = ? AND balance >= ?", (amount, now, CASH_ACCOUNT, amount))
            if cur.rowcount != 1:
                return finish("refused", f"Refused: ${amount:,.2f} exceeds the cash balance of "
                                         f"${cash_balance(conn):,.2f}. Cash can never go negative.")

            pay = conn.execute("INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) "
                               "VALUES (?,?,?,?,?,?)",
                               (r["kind"], r["ref_id"] if r["ref_id"] is not None else request_id,
                                amount, CASH_ACCOUNT, now, approver))
            if r["kind"] == "invoice":
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (r["ref_id"],))
            elif r["kind"] == "rent":
                lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (r["ref_id"],)).fetchone()
                conn.execute("UPDATE leases SET next_due = ? WHERE id = ?",
                             (add_month(date.fromisoformat(lease["next_due"])).isoformat(), r["ref_id"]))
            return finish("approved", f"Approved by {approver}; ${amount:,.2f} paid from {CASH_ACCOUNT}.",
                          pay.lastrowid)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
