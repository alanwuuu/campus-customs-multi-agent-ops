// Turn the raw audit trail into what the dashboard shows: the latest run for a ticket,
// each agent's live state, per-agent summaries, and the delegation graph.
import type { AuditEvent, TicketOutcome } from './api'
import { AGENTS, type AgentId, isAgent } from './agents'

/** Events (oldest first) belonging to the most recent agent run of one ticket, plus later human decisions. */
export function latestRunEvents(eventsNewestFirst: AuditEvent[], ticketId: number): AuditEvent[] {
  const asc = [...eventsNewestFirst].reverse()
  let start = -1
  for (let i = asc.length - 1; i >= 0; i--) {
    if (asc[i].event === 'ticket_started' && asc[i].ticket_id === ticketId) {
      start = i
      break
    }
  }
  if (start < 0) return []
  const runId = asc[start].run_id
  return asc
    .slice(start)
    .filter((e) => e.ticket_id === ticketId && (e.run_id === runId || e.event.startsWith('approval_')))
}

export type AgentState = 'idle' | 'thinking' | 'waiting' | 'done' | 'failed'

export interface AgentLive {
  state: AgentState
  detail: string
  lastTool?: string
}

const shortTask = (t?: string) => (t && t.length > 90 ? `${t.slice(0, 90)}…` : t ?? '')

/** Replays the run as a call stack: the agent on top is thinking, the ones below wait on it. */
export function agentLiveStates(events: AuditEvent[]): Record<AgentId, AgentLive> {
  const live = Object.fromEntries(
    AGENTS.map((a) => [a.id, { state: 'idle', detail: 'Not involved yet' } as AgentLive]),
  ) as Record<AgentId, AgentLive>
  const stack: AgentId[] = []

  for (const e of events) {
    const who = isAgent(e.agent) ? e.agent : null
    switch (e.event) {
      case 'ticket_started':
        stack.splice(0, stack.length, 'boss')
        live.boss = { state: 'thinking', detail: 'Reading the ticket' }
        break
      case 'tool_call':
        if (who) live[who] = { ...live[who], detail: `Used ${e.tool}`, lastTool: e.tool }
        break
      case 'tool_denied':
        if (who) live[who] = { ...live[who], detail: `Blocked from ${e.tool}` }
        break
      case 'delegation':
        if (who && isAgent(e.to)) {
          live[who] = { ...live[who], state: 'waiting', detail: `Waiting on ${label(e.to)}` }
          live[e.to] = { state: 'thinking', detail: `From ${label(who)}: ${shortTask(e.task)}` }
          stack.push(e.to)
        }
        break
      case 'delegation_refused':
        if (who) live[who] = { ...live[who], detail: `Hand-off refused: ${e.reason ?? ''}` }
        break
      case 'delegation_result':
        if (who) {
          const idx = stack.lastIndexOf(who)
          if (idx >= 0) stack.splice(idx, 1)
          live[who] = { ...live[who], state: 'done', detail: `Reported to ${label(e.reported_to)}` }
          if (isAgent(e.reported_to))
            live[e.reported_to] = { ...live[e.reported_to], state: 'thinking', detail: `Reviewing ${label(who)}'s report` }
        }
        break
      case 'ticket_finished':
        stack.length = 0
        live.boss = { ...live.boss, state: 'done', detail: `Decided: ${e.outcome?.status.replace('_', ' ') ?? 'done'}` }
        break
      case 'ticket_failed':
        for (const id of stack) live[id] = { ...live[id], state: 'failed', detail: 'Run failed' }
        stack.length = 0
        live.boss = { ...live.boss, state: 'failed', detail: e.error ?? 'Run failed' }
        break
    }
  }
  return live
}

function label(id?: string | null) {
  return AGENTS.find((a) => a.id === id)?.name ?? id ?? 'someone'
}

export interface AgentSummary {
  involved: boolean
  tools: Record<string, number>
  delegatedTo: AgentId[]
  receivedFrom: AgentId[]
  report?: string
}

export function agentSummaries(events: AuditEvent[]): Record<AgentId, AgentSummary> {
  const s = Object.fromEntries(
    AGENTS.map((a) => [a.id, { involved: false, tools: {}, delegatedTo: [], receivedFrom: [] } as AgentSummary]),
  ) as Record<AgentId, AgentSummary>
  for (const e of events) {
    const who = isAgent(e.agent) ? e.agent : null
    if (e.event === 'ticket_started') s.boss.involved = true
    if (e.event === 'tool_call' && who && e.tool) {
      s[who].involved = true
      s[who].tools[e.tool] = (s[who].tools[e.tool] ?? 0) + 1
    }
    if (e.event === 'delegation' && who && isAgent(e.to)) {
      s[who].delegatedTo.push(e.to)
      s[e.to].receivedFrom.push(who)
      s[e.to].involved = true
    }
    if (e.event === 'delegation_result' && who) s[who].report = asText(e.output)
    if (e.event === 'ticket_finished' && e.outcome) s.boss.report = e.outcome.decision
  }
  return s
}

export interface Edge {
  from: AgentId
  to: AgentId
  count: number
  firstStep: number
}

export function delegationEdges(events: AuditEvent[]): Edge[] {
  const map = new Map<string, Edge>()
  let step = 0
  for (const e of events) {
    if (e.event !== 'delegation' || !isAgent(e.agent) || !isAgent(e.to)) continue
    step += 1
    const key = `${e.agent}>${e.to}`
    const edge = map.get(key)
    if (edge) edge.count += 1
    else map.set(key, { from: e.agent, to: e.to, count: 1, firstStep: step })
  }
  return [...map.values()]
}

export function finishedOutcome(events: AuditEvent[]): { outcome?: TicketOutcome; usage?: AuditEvent['usage'] } {
  const done = [...events].reverse().find((e) => e.event === 'ticket_finished')
  return { outcome: done?.outcome, usage: done?.usage }
}

export function asText(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  return JSON.stringify(v, null, 2)
}
