import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, money, type Approval, type AuditEvent, type Cash, type Draft, type Health, type Run, type Ticket } from './api'
import { AGENTS, type AgentId } from './agents'
import { agentLiveStates, agentSummaries, delegationEdges, finishedOutcome, latestRunEvents } from './derive'
import { ActivityFeed } from './components/ActivityFeed'
import { DraftsPanel } from './components/Drafts'
import { ApprovalsTray, CashRegister } from './components/Money'
import { AgentFloor, AgentSummaries, DelegationMap } from './components/Team'
import { StatusStamp, TicketBoard } from './components/TicketBoard'

const FAST_MS = 1200 // while agents are working
const SLOW_MS = 5000 // idle desk

interface Toast {
  id: number
  tone: 'ok' | 'bad' | 'info'
  text: string
}

function readApprover() {
  try {
    return localStorage.getItem('cc-approver') ?? ''
  } catch {
    return ''
  }
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [dateToday, setDateToday] = useState('')
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [activeRun, setActiveRun] = useState<Run | null>(null)
  const [selectedId, setSelectedId] = useState(101)
  const [rawEvents, setRawEvents] = useState<AuditEvent[]>([])
  const [offline, setOffline] = useState(false)
  const [lastResetAt, setLastResetAt] = useState<string | null>(null)
  const [approver, setApprover] = useState(readApprover)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)
  const announced = useRef(new Set<string>())

  const running = activeRun?.status === 'running' || activeRun?.status === 'queued'

  const toast = useCallback((tone: Toast['tone'], text: string) => {
    const id = ++toastId.current
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5200)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [h, t, c, a, d, r, ev, rs] = await Promise.all([
        api.health(),
        api.tickets(),
        api.cash(),
        api.approvals(),
        api.drafts(),
        api.runs(),
        api.activity(selectedId),
        api.lastReset(),
      ])
      setLastResetAt(rs.events[0]?.timestamp ?? null)
      setHealth(h)
      setTickets(t.tickets)
      setDateToday(t.date_today)
      setCash(c)
      setApprovals(a.requests)
      setDrafts(d.drafts)
      setRawEvents(ev.events)
      const live = r.runs.find((x) => x.status === 'running' || x.status === 'queued')
      setActiveRun((prev) => {
        if (live) return live
        if (prev && (prev.status === 'running' || prev.status === 'queued')) {
          const done = r.runs.find((x) => x.run_id === prev.run_id)
          if (done) {
            if (announced.current.has(done.run_id)) return done
            announced.current.add(done.run_id)
            if (done.status === 'failed') toast('bad', `Run failed: ${done.error}`)
            else toast('ok', `Agents finished ticket${done.ticket_ids.length > 1 ? 's' : ''} ${done.ticket_ids.map((i) => '#' + i).join(', ')}`)
            return done
          }
        }
        return prev
      })
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [selectedId, toast])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, running ? FAST_MS : SLOW_MS)
    return () => clearInterval(id)
  }, [refresh, running])

  // While a full run is going, follow the ticket the agents are on.
  useEffect(() => {
    if (running && activeRun?.current_ticket && activeRun.ticket_ids.length > 1) setSelectedId(activeRun.current_ticket)
  }, [running, activeRun?.current_ticket, activeRun?.ticket_ids.length])

  const saveApprover = (v: string) => {
    setApprover(v)
    try {
      localStorage.setItem('cc-approver', v)
    } catch {
      /* per-viewer convenience only */
    }
  }

  const startRun = async () => {
    try {
      const run = await api.runTicket(selectedId)
      setActiveRun(run)
      toast('info', `Boss is picking up ticket #${selectedId}`)
      refresh()
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  const startFullRun = async () => {
    if (!window.confirm('Full run: reset the working database to the original values, then run tickets 101 → 102 → 103?')) return
    try {
      const run = await api.runAll()
      setActiveRun(run)
      setSelectedId(101)
      toast('info', 'Database reset. Full run started.')
      refresh()
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  const reset = async () => {
    if (!window.confirm('Reset campus_customs_new.db to the original values? Approvals, drafts and payments are cleared (the audit trail is kept).')) return
    try {
      const r = await api.reset()
      toast('ok', `Database reset · checking back to ${money(r.checking_balance)}`)
      refresh()
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  const decide = async (id: number, approve: boolean) => {
    try {
      const r = await api.decide(id, approve, approver.trim())
      toast(r.status === 'approved' ? 'ok' : r.status === 'refused' ? 'bad' : 'info', r.result)
    } catch (e) {
      toast('bad', (e as Error).message)
    }
    await refresh()
  }

  const events = useMemo(() => latestRunEvents(rawEvents, selectedId), [rawEvents, selectedId])
  const live = useMemo(() => agentLiveStates(events), [events])
  const summaries = useMemo(() => agentSummaries(events), [events])
  const edges = useMemo(() => delegationEdges(events), [events])
  const { outcome, usage } = useMemo(() => finishedOutcome(events), [events])
  const involved = useMemo(
    () => new Set(AGENTS.filter((a) => summaries[a.id].involved).map((a) => a.id as AgentId)),
    [summaries],
  )
  const stale = events.length > 0 && lastResetAt != null && events[0].timestamp < lastResetAt
  const selected = tickets.find((t) => t.id === selectedId)
  const runningHere = running && activeRun?.current_ticket === selectedId
  const pendingCount = approvals.filter((a) => a.status === 'pending').length

  return (
    <div className="desk">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            CC
          </span>
          <div>
            <h1>
              Campus Customs <span>Ops Desk</span>
            </h1>
            <p>Chapel Street · multi-agent operations</p>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="chip">
            Desk date <b>{dateToday || '—'}</b>
          </span>
          <span className="chip">
            Model <b>{health?.model ?? '—'}</b>
          </span>
          <span className={`chip ${offline ? 'chip-bad' : running ? 'chip-live' : 'chip-ok'}`}>
            {offline ? 'Backend offline' : running ? `Agents on #${activeRun?.current_ticket ?? '…'}` : 'Team idle'}
          </span>
          <span className={`chip${pendingCount ? ' chip-warn' : ''}`}>
            <b>{pendingCount}</b> awaiting approval
          </span>
        </div>
        <div className="topbar-actions">
          <button className="btn btn-ghost" onClick={reset} disabled={running}>
            Reset DB
          </button>
          <button className="btn btn-outline" onClick={startFullRun} disabled={running || offline}>
            Full run
          </button>
        </div>
      </header>

      {offline && (
        <div className="offline">
          Can’t reach the FastAPI backend. Start it from <code>HW5/</code> with{' '}
          <code>.venv/Scripts/python backend/main.py</code>.
        </div>
      )}

      <main className="layout">
        <aside className="col-left">
          <TicketBoard tickets={tickets} selectedId={selectedId} runningTicket={running ? activeRun?.current_ticket ?? null : null} onSelect={setSelectedId} />
        </aside>

        <section className="col-center">
          {selected && (
            <div className="panel ticket-bar">
              <div className="ticket-bar-info">
                <span className="ticket-bar-no">#{selected.id}</span>
                <div>
                  <h2>{selected.subject}</h2>
                  <p>
                    {selected.requester}
                    {selected.notes ? ` · ${selected.notes.split('\n')[0]}` : ''}
                  </p>
                </div>
              </div>
              <div className="ticket-bar-actions">
                <StatusStamp status={selected.status} />
                <button className="btn btn-primary" onClick={startRun} disabled={running || offline}>
                  {runningHere ? (
                    <>
                      <span className="spinner" aria-hidden="true" /> Agents working…
                    </>
                  ) : (
                    'Run agents'
                  )}
                </button>
              </div>
            </div>
          )}
          <AgentFloor live={live} running={runningHere} />
          <div className="split">
            <DelegationMap edges={edges} live={live} involved={involved} />
            <AgentSummaries summaries={summaries} outcome={outcome} usage={usage} stale={stale} />
          </div>
          <ActivityFeed events={events} running={runningHere} />
        </section>

        <aside className="col-right">
          <CashRegister cash={cash} />
          <ApprovalsTray
            approvals={approvals}
            balance={cash?.checking_balance ?? 0}
            openInvoiceIds={cash?.obligations.filter((o) => o.kind === 'invoice').map((o) => o.ref_id) ?? []}
            busy={running}
            approver={approver}
            onApprover={saveApprover}
            onDecide={decide}
          />
          <DraftsPanel drafts={drafts} ticketId={selectedId} />
        </aside>
      </main>

      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </div>
  )
}
