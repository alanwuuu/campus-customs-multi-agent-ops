import type { AuditEvent } from '../api'
import { money } from '../api'
import { AgentBadge } from '../agents'
import { asText } from '../derive'

const IDENTITY = new Set(['requested_by', 'author', 'updated_by'])

function argSummary(args: AuditEvent['args']): string {
  if (!args || typeof args === 'string') return ''
  return Object.entries(args)
    .filter(([k]) => !IDENTITY.has(k) && k !== 'body' && k !== 'note' && k !== 'reason')
    .map(([, v]) => (typeof v === 'string' ? `"${v.length > 24 ? v.slice(0, 24) + '…' : v}"` : String(v)))
    .join(', ')
}

const time = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })

function Line({ e }: { e: AuditEvent }) {
  switch (e.event) {
    case 'ticket_started':
      return (
        <>
          <AgentBadge id="boss" compact /> picked up ticket <b>#{e.ticket_id}</b>
        </>
      )
    case 'tool_call':
      return (
        <>
          <AgentBadge id={e.agent} compact /> <span className="verb">called</span>{' '}
          <code className="tool">
            {e.tool}({argSummary(e.args)})
          </code>
        </>
      )
    case 'tool_denied':
      return (
        <>
          <AgentBadge id={e.agent} compact /> <span className="warn-text">was denied</span> <code className="tool">{e.tool}</code>
        </>
      )
    case 'delegation':
      return (
        <>
          <AgentBadge id={e.agent} compact /> <span className="verb">handed off to</span> <AgentBadge id={e.to} compact />
        </>
      )
    case 'delegation_result':
      return (
        <>
          <AgentBadge id={e.agent} compact /> <span className="verb">reported back to</span> <AgentBadge id={e.reported_to} compact />
        </>
      )
    case 'delegation_refused':
      return (
        <>
          <AgentBadge id={e.agent} compact /> <span className="warn-text">hand-off to {e.to} refused</span>
        </>
      )
    case 'ticket_finished':
      return (
        <>
          <AgentBadge id="boss" compact /> closed out the run · <b>{e.outcome?.status.replace('_', ' ')}</b>
        </>
      )
    case 'ticket_failed':
      return (
        <>
          <AgentBadge id="boss" compact /> <span className="warn-text">run failed</span>
        </>
      )
    case 'approval_approved':
    case 'approval_refused':
    case 'approval_rejected':
      return (
        <>
          <AgentBadge id="human" compact /> <b>{e.approver}</b> {e.event.replace('approval_', '')} request #{e.request_id} ·{' '}
          {e.kind} {e.amount != null && money(e.amount)}
        </>
      )
    case 'database_reset':
      return <>Working database reset to original values</>
    default:
      return <>{e.event}</>
  }
}

function Detail({ e }: { e: AuditEvent }) {
  let body: string | null = null
  if (e.event === 'tool_call') body = `args ${asText(e.args)}\n\nresult ${asText(e.result)}`
  else if (e.event === 'delegation') body = e.task ?? null
  else if (e.event === 'delegation_result') body = asText(e.output)
  else if (e.event === 'ticket_failed') body = e.error ?? null
  else if (e.event.startsWith('approval_')) body = asText(e.result)
  else if (e.event === 'delegation_refused') body = e.reason ?? null
  if (!body) return null
  const inline = e.event === 'delegation'
  return inline ? (
    <p className="feed-task">“{body}”</p>
  ) : (
    <details className="feed-detail">
      <summary>{e.event === 'tool_call' ? 'Show data' : 'Show text'}</summary>
      <pre>{body}</pre>
    </details>
  )
}

export function ActivityFeed({ events, running }: { events: AuditEvent[]; running: boolean }) {
  const newestFirst = [...events].reverse()
  return (
    <section className="panel feed" aria-labelledby="feed-title">
      <header className="panel-head">
        <h2 id="feed-title">Live wire</h2>
        <span className="tally">
          {running && <span className="live-dot">live</span>} {events.length} events
        </span>
      </header>
      {events.length === 0 ? (
        <p className="empty-note">Quiet desk. Select a ticket and press “Run agents”.</p>
      ) : (
        <ol className="feed-list" aria-live="polite">
          {newestFirst.map((e, i) => (
            <li key={`${e.timestamp}-${i}`} className={`feed-item ev-${e.event}`}>
              <time>{time(e.timestamp)}</time>
              <div>
                <div className="feed-line">
                  <Line e={e} />
                </div>
                <Detail e={e} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
