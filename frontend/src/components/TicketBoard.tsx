import type { Ticket, TicketStatus } from '../api'

export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_approval: 'Needs approval',
  blocked: 'Blocked',
  resolved: 'Resolved',
}

const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export function StatusStamp({ status }: { status: TicketStatus }) {
  return <span className={`stamp stamp-${status}`}>{STATUS_LABEL[status]}</span>
}

interface Props {
  tickets: Ticket[]
  selectedId: number
  runningTicket: number | null
  onSelect: (id: number) => void
}

export function TicketBoard({ tickets, selectedId, runningTicket, onSelect }: Props) {
  const resolved = tickets.filter((t) => t.is_resolved).length
  return (
    <section className="panel board" aria-labelledby="board-title">
      <header className="panel-head">
        <h2 id="board-title">Ticket rail</h2>
        <span className="tally">
          <b>{tickets.length - resolved}</b> open · <b>{resolved}</b> resolved
        </span>
      </header>
      <ol className="rail">
        {tickets.map((t) => {
          const selected = t.id === selectedId
          const working = t.id === runningTicket
          return (
            <li key={t.id}>
              <button
                className={`ticket${selected ? ' selected' : ''}${working ? ' working' : ''}`}
                onClick={() => onSelect(t.id)}
                aria-pressed={selected}
              >
                <span className="ticket-top">
                  <span className="ticket-no">#{t.id}</span>
                  <span className={`openness ${t.is_resolved ? 'is-resolved' : 'is-open'}`}>
                    {t.is_resolved ? '✓ Resolved' : '● Open'}
                  </span>
                </span>
                <span className="ticket-subject">{t.subject}</span>
                <span className="ticket-meta">
                  {TYPE_LABEL[t.type] ?? t.type} · {t.requester}
                </span>
                {t.sku && (
                  <span className="ticket-sku">
                    {t.qty}× {t.sku} · {t.size}
                  </span>
                )}
                <span className="ticket-foot">
                  <StatusStamp status={t.status} />
                  {working && <span className="live-dot">agents working</span>}
                  {!working && t.pending_approvals > 0 && (
                    <span className="pill pill-warn">{t.pending_approvals} to approve</span>
                  )}
                  {!working && t.drafts > 0 && <span className="pill">{t.drafts} draft{t.drafts > 1 ? 's' : ''}</span>}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
