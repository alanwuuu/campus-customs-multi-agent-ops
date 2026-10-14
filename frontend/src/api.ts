// Typed client for the FastAPI backend (backend/main.py). Vite proxies /api to it.

export type TicketStatus = 'open' | 'in_progress' | 'waiting_approval' | 'blocked' | 'resolved'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: TicketStatus
  notes: string | null
  created_at: string
  is_resolved: boolean
  pending_approvals: number
  drafts: number
}

export interface AuditEvent {
  timestamp: string
  run_id: string | null
  ticket_id: number | null
  agent: string | null
  event: string
  tool?: string
  args?: Record<string, unknown> | string
  result?: unknown
  to?: string
  task?: string
  chain?: string[]
  output?: unknown
  reported_to?: string
  reason?: string
  outcome?: TicketOutcome
  usage?: { requests: number; tool_calls: number; input_tokens: number; output_tokens: number; total_tokens: number }
  delegations?: number
  error?: string
  approver?: string
  request_id?: number
  kind?: string
  payee?: string
  amount?: number
  cash_balance?: number
  detail?: string
  model?: string
}

export interface TicketOutcome {
  ticket_id: number
  status: TicketStatus
  agents_used: string[]
  decision: string
  actions: string[]
  approval_request_ids: number[]
  draft_ids: number[]
}

export interface Run {
  run_id: string
  ticket_ids: number[]
  status: 'queued' | 'running' | 'finished' | 'failed'
  current_ticket: number | null
  outcomes: TicketOutcome[]
  error: string | null
  started_at: string
  finished_at: string | null
  reset_first: boolean
}

export interface Approval {
  id: number
  ticket_id: number | null
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number | null
  vendor_id: number | null
  payee: string
  amount: number
  details: Record<string, unknown> | null
  status: 'pending' | 'approved' | 'rejected' | 'refused'
  requested_by: string
  reason: string | null
  created_at: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  payment_id: number | null
}

export interface Obligation {
  kind: 'invoice' | 'rent'
  ref_id: number
  payee: string
  amount: number
  due_date: string
  days_until_due: number
  overdue: boolean
  description: string
  balance_after_if_paid: number
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
}

export interface Cash {
  date_today: string
  checking_balance: number
  obligations: Obligation[]
  total_obligations: number
  pending_approval_requests: Approval[]
  balance_if_all_pending_approved: number
  payments: Payment[]
}

export interface Draft {
  id: number
  ticket_id: number | null
  recipient: string
  recipient_type: string
  subject: string
  body: string
  author: string
  status: string
  created_at: string
}

export interface Health {
  ok: boolean
  model: string
  database: string
  agent_running: boolean
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') detail = data.detail
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* keep status text */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const get = <T,>(path: string) => request<T>('GET', path)
const post = <T,>(path: string, body?: unknown) => request<T>('POST', path, body ?? {})

export const api = {
  health: () => get<Health>('/api/health'),
  tickets: () => get<{ date_today: string; tickets: Ticket[] }>('/api/tickets'),
  activity: (ticketId: number, limit = 500) =>
    get<{ total: number; events: AuditEvent[] }>(`/api/activity?ticket_id=${ticketId}&limit=${limit}`),
  lastReset: () => get<{ total: number; events: AuditEvent[] }>('/api/activity?event=database_reset&limit=1'),
  runTicket: (id: number) => post<Run>(`/api/tickets/${id}/run`),
  runAll: () => post<Run>('/api/run-all', { reset_first: true }),
  runs: () => get<{ agent_running: boolean; runs: Run[] }>('/api/runs'),
  approvals: () => get<{ cash_balance: number; requests: Approval[] }>('/api/approvals?status=all'),
  decide: (id: number, approve: boolean, approver: string, note = '') =>
    post<{ status: string; result: string; cash_balance: number }>(
      `/api/approvals/${id}/${approve ? 'approve' : 'reject'}`,
      { approver, note },
    ),
  cash: () => get<Cash>('/api/cash'),
  drafts: () => get<{ drafts: Draft[] }>('/api/drafts'),
  reset: () => post<{ ok: boolean; checking_balance: number }>('/api/reset'),
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
