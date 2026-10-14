import type { AuditEvent, TicketOutcome } from '../api'
import { AGENTS, AGENT_BY_ID, AgentBadge, AgentGlyph, type AgentId } from '../agents'
import { type AgentLive, type AgentSummary, type Edge } from '../derive'
import { StatusStamp } from './TicketBoard'

const STATE_LABEL: Record<AgentLive['state'], string> = {
  idle: 'Idle',
  thinking: 'Working',
  waiting: 'Waiting',
  done: 'Done',
  failed: 'Failed',
}

/** The five agent stations along the counter, each showing its live state. */
export function AgentFloor({ live, running }: { live: Record<AgentId, AgentLive>; running: boolean }) {
  return (
    <section className="panel floor" aria-label="Agent stations">
      <ul className="stations">
        {AGENTS.map((a) => {
          const s = live[a.id]
          const active = running && s.state === 'thinking'
          return (
            <li
              key={a.id}
              className={`station state-${s.state}${active ? ' active' : ''}`}
              style={{ '--agent': a.color } as React.CSSProperties}
            >
              <div className="station-head">
                <span className="avatar">
                  <AgentGlyph id={a.id} size={24} />
                </span>
                <span className="station-name">
                  {a.name}
                  <small>{a.role}</small>
                </span>
              </div>
              <div className="station-state">
                <span className="state-chip">{active ? 'Working…' : STATE_LABEL[s.state]}</span>
              </div>
              <p className="station-detail" title={s.detail}>
                {s.detail}
              </p>
              {s.lastTool && <code className="station-tool">{s.lastTool}</code>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// Pentagon layout, Boss at the top.
const POS: Record<AgentId, [number, number]> = {
  boss: [160, 38],
  inventory: [284, 124],
  accounting: [236, 262],
  facilities: [84, 262],
  customer_service: [36, 124],
}
const R = 24

/** Who handed work to whom in the latest run. Edges are numbered in the order they first happened. */
export function DelegationMap({ edges, live, involved }: { edges: Edge[]; live: Record<AgentId, AgentLive>; involved: Set<AgentId> }) {
  return (
    <section className="panel map" aria-labelledby="map-title">
      <header className="panel-head">
        <h2 id="map-title">Hand-off map</h2>
        <span className="tally">{edges.reduce((n, e) => n + e.count, 0)} delegations</span>
      </header>
      <svg viewBox="-24 0 368 300" role="img" aria-label="Delegation graph between agents">
        <defs>
          {AGENTS.map((a) => (
            <marker key={a.id} id={`arrow-${a.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 10 5 0 10z" fill={a.color} />
            </marker>
          ))}
        </defs>
        {edges.map((e) => {
          const [x1, y1] = POS[e.from]
          const [x2, y2] = POS[e.to]
          const dx = x2 - x1
          const dy = y2 - y1
          const len = Math.hypot(dx, dy)
          const ux = dx / len
          const uy = dy / len
          // bow the curve so A->B and B->A don't overlap
          const mx = (x1 + x2) / 2 - uy * 22
          const my = (y1 + y2) / 2 + ux * 22
          const sx = x1 + ux * R
          const sy = y1 + uy * R
          const ex = x2 - ux * (R + 4)
          const ey = y2 - uy * (R + 4)
          const color = AGENT_BY_ID[e.from].color
          return (
            <g key={`${e.from}-${e.to}`} className="edge">
              <path d={`M${sx} ${sy} Q${mx} ${my} ${ex} ${ey}`} stroke={color} strokeWidth={1.6 + e.count} fill="none" markerEnd={`url(#arrow-${e.from})`} />
              <circle cx={mx} cy={my} r="9" className="edge-step" stroke={color} />
              <text x={mx} y={my + 3.5} textAnchor="middle" className="edge-step-text">
                {e.firstStep}
              </text>
            </g>
          )
        })}
        {AGENTS.map((a) => {
          const [x, y] = POS[a.id]
          const s = live[a.id].state
          return (
            <g
              key={a.id}
              className={`node state-${s}${involved.has(a.id) ? ' involved' : ' bystander'}`}
              style={{ '--agent': a.color, color: a.color } as React.CSSProperties}
              transform={`translate(${x} ${y})`}
            >
              <circle r={R} className="node-ring" />
              <g transform="translate(-11 -11)">
                <AgentGlyph id={a.id} size={22} />
              </g>
              <text y={R + 14} textAnchor="middle" className="node-label">
                {a.name}
              </text>
            </g>
          )
        })}
      </svg>
      {edges.length === 0 && <p className="empty-note">No hand-offs yet. Run the team to see who calls whom.</p>}
    </section>
  )
}

/** One card per agent: what it touched, who it worked with, and what it reported. */
export function AgentSummaries({
  summaries,
  outcome,
  usage,
  stale,
}: {
  summaries: Record<AgentId, AgentSummary>
  outcome?: TicketOutcome
  usage?: AuditEvent['usage']
  stale?: boolean
}) {
  const involved = AGENTS.filter((a) => summaries[a.id].involved)
  const benched = AGENTS.filter((a) => !summaries[a.id].involved)
  return (
    <section className="panel summaries" aria-labelledby="sum-title">
      <header className="panel-head">
        <h2 id="sum-title">Shift report</h2>
        {usage && (
          <span className="tally">
            {usage.requests} model calls · {usage.tool_calls} tools · {usage.total_tokens.toLocaleString()} tokens
          </span>
        )}
      </header>

      {stale && (
        <p className="stale-note">This run happened before the last database reset. Its approvals and drafts were cleared; run the ticket again for a fresh result.</p>
      )}
      {outcome && (
        <div className="verdict">
          <div className="verdict-head">
            <AgentBadge id="boss" />
            <span>final decision</span>
            <StatusStamp status={outcome.status} />
          </div>
          <p>{outcome.decision}</p>
          {outcome.actions.length > 0 && (
            <ul className="actions">
              {outcome.actions.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {involved.length === 0 && <p className="empty-note">No agent has worked this ticket yet.</p>}
      <div className="sum-grid">
        {involved.map((a) => {
          const s = summaries[a.id]
          return (
            <article key={a.id} className="sum-card" style={{ '--agent': a.color } as React.CSSProperties}>
              <header>
                <AgentBadge id={a.id} />
              </header>
              <dl>
                {s.receivedFrom.length > 0 && (
                  <>
                    <dt>Called by</dt>
                    <dd>{[...new Set(s.receivedFrom)].map((x) => <AgentBadge key={x} id={x} compact />)}</dd>
                  </>
                )}
                {s.delegatedTo.length > 0 && (
                  <>
                    <dt>Handed off to</dt>
                    <dd>{[...new Set(s.delegatedTo)].map((x) => <AgentBadge key={x} id={x} compact />)}</dd>
                  </>
                )}
                <dt>MCP tools</dt>
                <dd className="tool-list">
                  {Object.keys(s.tools).length === 0 ? (
                    <span className="muted">none</span>
                  ) : (
                    Object.entries(s.tools).map(([t, n]) => (
                      <code key={t}>
                        {t}
                        {n > 1 && <b>×{n}</b>}
                      </code>
                    ))
                  )}
                </dd>
              </dl>
              {s.report && a.id !== 'boss' && (
                <details className="report">
                  <summary>Report</summary>
                  <p>{s.report}</p>
                </details>
              )}
            </article>
          )
        })}
      </div>
      {benched.length > 0 && involved.length > 0 && (
        <p className="benched">
          Not needed for this ticket: {benched.map((a) => <AgentBadge key={a.id} id={a.id} compact />)}
        </p>
      )}
    </section>
  )
}
