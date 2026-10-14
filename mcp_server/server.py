"""Campus Customs MCP server (FastMCP).

Gives the agent team access to the working database `data/campus_customs_new.db`.
The database logic and rule enforcement live in `shop_db.py`; this file only
exposes them as MCP tools.

Read tools:   get_open_tickets, get_ticket_context, check_stock_and_restock,
              get_cash_position, quote_discount
Write tools:  request_payment, request_purchase_order, create_draft,
              update_ticket_status

Agents can only *request* payments. Approving one (`shop_db.decide_approval`)
is a human action and is deliberately not exposed as an MCP tool.

Run:  python mcp_server/server.py   (stdio; see HW5/.mcp.json)
"""
from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

import shop_db

mcp = FastMCP("campus-customs")


# ---------------------------------------------------------------- read tools

@mcp.tool
def get_open_tickets() -> dict:
    """List every ticket that is not resolved yet (id, type, requester, subject, status), plus desk.date_today."""
    return shop_db.get_open_tickets()


@mcp.tool
def get_ticket_context(ticket_id: int) -> dict:
    """Return one ticket plus all linked database facts.

    Includes the shop date, the ticket row, and, when present, the linked
    product (stock in that size, pricing, margin), the linked invoice
    (with overdue status), the linked lease (with days until rent is due),
    and any approval requests / drafts already created for this ticket.
    Use this first on any ticket to decide which agents should work on it.
    """
    return shop_db.get_ticket_context(ticket_id)


@mcp.tool
def check_stock_and_restock(sku: str, size: str, qty_needed: int) -> dict:
    """Check stock for a SKU and size and plan a restock if short.

    Returns units on hand, the shortage, the matching vendor from the vendors
    table, purchase-order cost (shortage x unit_cost), expected arrival
    (desk.date_today + vendors.lead_days), and whether the vendor is blocked
    from shipping because it has an open unpaid invoice.
    """
    return shop_db.check_stock_and_restock(sku, size, qty_needed)


@mcp.tool
def get_cash_position() -> dict:
    """Return cash on hand versus everything the shop currently owes.

    Lists open vendor invoices and upcoming rent with days until due /
    days overdue (from desk.date_today), sorted by due date, plus the
    projected balance after paying each in order and all approval requests
    still pending. A negative projection means that payment would have to be
    refused: cash can never go negative.
    """
    return shop_db.get_cash_position()


@mcp.tool
def quote_discount(sku: str, qty: int, discount_pct: float) -> dict:
    """Price a discounted order: discounted unit price, order total, savings, and margin after discount.

    Flags `sells_below_cost` and gives the maximum discount that avoids a loss.
    Use it before recommending or deciding on any price override.
    """
    return shop_db.quote_discount(sku, qty, discount_pct)


# ---------------------------------------------------------------- write tools

@mcp.tool
def request_payment(ticket_id: int, kind: Literal["invoice", "rent"], ref_id: int,
                    requested_by: str, reason: str) -> dict:
    """Queue a vendor-invoice or rent payment for HUMAN approval. No money moves.

    ref_id is the invoice id (kind='invoice') or lease id (kind='rent'). The
    amount is read from the database, not supplied by the agent. The request is
    REFUSED immediately if the amount exceeds the cash balance. Duplicate
    requests for the same invoice/lease are not created.
    """
    return shop_db.request_payment(ticket_id, kind, ref_id, requested_by, reason)


@mcp.tool
def request_purchase_order(ticket_id: int, sku: str, size: str, qty: int,
                           requested_by: str, reason: str) -> dict:
    """Queue a restock purchase order (qty x unit_cost) to the matching vendor for HUMAN approval.

    Refused if the cost exceeds the cash balance. If the vendor has an open
    unpaid invoice the PO is marked blocked and cannot be approved until that
    invoice is paid.
    """
    return shop_db.request_purchase_order(ticket_id, sku, size, qty, requested_by, reason)


@mcp.tool
def create_draft(ticket_id: int, recipient: str,
                 recipient_type: Literal["customer", "vendor", "landlord", "other"],
                 subject: str, body: str, author: str) -> dict:
    """Save a message to a customer, vendor or landlord as a DRAFT on the board. Nothing is ever sent."""
    return shop_db.create_draft(ticket_id, recipient, recipient_type, subject, body, author)


@mcp.tool
def update_ticket_status(ticket_id: int,
                         status: Literal["open", "in_progress", "waiting_approval", "blocked", "resolved"],
                         note: str, updated_by: str) -> dict:
    """Set a ticket's status and append a dated note explaining the decision (earlier notes are kept)."""
    return shop_db.update_ticket_status(ticket_id, status, note, updated_by)


if __name__ == "__main__":
    mcp.run(show_banner=False)
