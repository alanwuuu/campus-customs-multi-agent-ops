import type { Draft } from '../api'
import { AgentBadge } from '../agents'

export function DraftsPanel({ drafts, ticketId }: { drafts: Draft[]; ticketId: number }) {
  const mine = drafts.filter((d) => d.ticket_id === ticketId)
  return (
    <section className="panel drafts" aria-labelledby="drafts-title">
      <header className="panel-head">
        <h2 id="drafts-title">Outbox · drafts only</h2>
        <span className="tally">#{ticketId}</span>
      </header>
      {mine.length === 0 ? (
        <p className="empty-note">No drafts for this ticket.</p>
      ) : (
        <ul className="draft-list">
          {mine.map((d) => (
            <li key={d.id} className="draft">
              <details>
                <summary>
                  <span className="draft-to">
                    To {d.recipient} <span className="muted">({d.recipient_type})</span>
                  </span>
                  <span className="draft-subject">{d.subject}</span>
                </summary>
                <pre className="draft-body">{d.body}</pre>
              </details>
              <div className="draft-foot">
                <AgentBadge id={d.author} compact />
                <span className="not-sent">NOT SENT</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
