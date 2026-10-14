import { useEffect, useRef, useState } from 'react'
import type { Approval, Cash } from '../api'
import { money } from '../api'
import { AgentBadge } from '../agents'

/** Counts from the previous value to the new one so a payment visibly drains the register.
 *  The first real value is shown immediately, and a timer guarantees the final value even if
 *  animation frames are paused (background tab). */
function useTweened(value: number | null, ms = 900) {
  const [shown, setShown] = useState<number | null>(null)
  const from = useRef<number | null>(null)
  useEffect(() => {
    if (value == null) return
    if (from.current == null) {
      from.current = value
      setShown(value)
      return
    }
    const a = from.current
    const start = performance.now()
    let raf = 0
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / ms)
      setShown(a + (value - a) * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    const done = setTimeout(() => setShown(value), ms + 50)
    from.current = value
    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(done)
      setShown(value)
    }
  }, [value, ms])
  return shown ?? value ?? 0
}

export function CashRegister({ cash }: { cash: Cash | null }) {
  const balance = cash?.checking_balance ?? 0
  const shown = useTweened(cash ? balance : null)
  const prev = useRef<number | null>(null)
  const [flash, setFlash] = useState<'down' | 'up' | null>(null)

  useEffect(() => {
    if (cash == null) return
    if (prev.current != null && prev.current !== balance) {
      setFlash(balance < prev.current ? 'down' : 'up')
      const t = setTimeout(() => setFlash(null), 1600)
      prev.current = balance
      return () => clearTimeout(t)
    }
    prev.current = balance
  }, [balance, cash])

  const projected = cash?.balance_if_all_pending_approved ?? balance
  const pendingTotal = balance - projected
  const lastPayment = cash?.payments[0]

  return (
    <section className={`panel register${flash ? ` flash-${flash}` : ''}`} aria-labelledby="cash-title">
      <header className="panel-head">
        <h2 id="cash-title">Register</h2>
        <span className="tally">checking</span>
      </header>
      <div className="lcd" aria-live="polite">
        <span className="lcd-label">BALANCE</span>
        <span className="lcd-value">{cash ? money(shown) : '—'}</span>
      </div>
      <dl className="cash-lines">
        <div>
          <dt>Waiting on you</dt>
          <dd className={pendingTotal > 0 ? 'warn-text' : ''}>−{money(pendingTotal)}</dd>
        </div>
        <div>
          <dt>If all approved</dt>
          <dd className={projected < 0 ? 'bad-text' : ''}>{money(projected)}</dd>
        </div>
      </dl>
      {projected < 0 && (
        <p className="register-warn">
          Approving everything would overdraw checking. The register will refuse whichever payment crosses $0.
        </p>
      )}
      {lastPayment && (
        <p className="receipt-line">
          Last paid: {lastPayment.kind} {money(lastPayment.amount)} · approved by {lastPayment.approved_by}
        </p>
      )}
      {cash && cash.obligations.length > 0 && (
        <details className="obligations">
          <summary>Bills on the spike ({cash.obligations.length})</summary>
          <ul>
            {cash.obligations.map((o) => (
              <li key={`${o.kind}-${o.ref_id}`}>
                <span>
                  {o.kind === 'rent' ? 'Rent' : `Invoice ${o.ref_id}`} · {o.payee}
                </span>
                <span className={o.overdue ? 'bad-text' : o.days_until_due <= 3 ? 'warn-text' : ''}>
                  {money(o.amount)} ·{' '}
                  {o.overdue ? `${-o.days_until_due}d overdue` : `due in ${o.days_until_due}d`}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

const KIND_LABEL: Record<Approval['kind'], string> = {
  invoice: 'Vendor invoice',
  rent: 'Rent',
  purchase_order: 'Purchase order',
}

interface ApprovalsProps {
  approvals: Approval[]
  balance: number
  openInvoiceIds: number[]
  busy: boolean
  approver: string
  onApprover: (v: string) => void
  onDecide: (id: number, approve: boolean) => Promise<void>
}

export function ApprovalsTray({ approvals, balance, openInvoiceIds, busy, approver, onApprover, onDecide }: ApprovalsProps) {
  const [working, setWorking] = useState<number | null>(null)
  const pending = approvals.filter((a) => a.status === 'pending')
  const decided = approvals.filter((a) => a.status !== 'pending').slice(0, 6)
  const decide = async (id: number, approve: boolean) => {
    setWorking(id)
    try {
      await onDecide(id, approve)
    } finally {
      setWorking(null)
    }
  }
  const noName = approver.trim() === ''

  return (
    <section className="panel approvals" aria-labelledby="appr-title">
      <header className="panel-head">
        <h2 id="appr-title">Approval tray</h2>
        <span className={`tally${pending.length ? ' tally-hot' : ''}`}>{pending.length} waiting</span>
      </header>
      <label className="approver">
        <span>Signing as</span>
        <input value={approver} onChange={(e) => onApprover(e.target.value)} placeholder="Your name" maxLength={40} />
      </label>
      {pending.length === 0 && <p className="empty-note">Nothing needs your signature.</p>}
      <ul className="slips">
        {pending.map((a) => {
          const blockedBy = ((a.details?.blocked_by_open_invoices as number[] | undefined) ?? []).filter((id) => openInvoiceIds.includes(id))
          const overdraws = a.amount > balance
          return (
            <li key={a.id} className="slip">
              <div className="slip-top">
                <span className="slip-kind">{KIND_LABEL[a.kind]}</span>
                <span className="slip-amt">{money(a.amount)}</span>
              </div>
              <div className="slip-payee">
                {a.payee}
                {a.ticket_id != null && <span className="muted"> · ticket #{a.ticket_id}</span>}
              </div>
              {a.kind === 'purchase_order' && a.details && (
                <div className="slip-meta">
                  {String(a.details.qty)}× {String(a.details.sku)} {String(a.details.size)} · ETA{' '}
                  {String(a.details.eta_if_approved_today)}
                </div>
              )}
              {a.reason && <p className="slip-reason">{a.reason}</p>}
              <div className="slip-by">
                prepared by <AgentBadge id={a.requested_by} compact />
              </div>
              {blockedBy.length > 0 && <p className="slip-flag">Vendor blocked until invoice {blockedBy.join(', ')} is paid</p>}
              {overdraws && <p className="slip-flag bad">More than the {money(balance)} in checking. It will be refused.</p>}
              <div className="slip-actions">
                <button
                  className="btn btn-approve"
                  disabled={busy || noName || working === a.id}
                  onClick={() => decide(a.id, true)}
                  title={noName ? 'Enter your name first' : undefined}
                >
                  {working === a.id ? '…' : 'Approve & pay'}
                </button>
                <button className="btn btn-ghost" disabled={busy || noName || working === a.id} onClick={() => decide(a.id, false)}>
                  Reject
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      {busy && pending.length > 0 && <p className="hint">Approvals unlock when the agents finish their run.</p>}
      {decided.length > 0 && (
        <details className="decided">
          <summary>Recently decided</summary>
          <ul>
            {decided.map((a) => (
              <li key={a.id}>
                <span className={`mini-stamp mini-${a.status}`}>{a.status}</span> {KIND_LABEL[a.kind]} {money(a.amount)} ·{' '}
                {a.decided_by}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
