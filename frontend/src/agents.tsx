// Visual identity for each agent: color + glyph + call sign, so agents are distinguishable
// by shape and text as well as hue (color is never the only cue).

export type AgentId = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface AgentMeta {
  id: AgentId
  name: string
  short: string // two-letter call sign shown on badges
  role: string
  color: string
}

export const AGENTS: AgentMeta[] = [
  { id: 'boss', name: 'Boss', short: 'BS', role: 'Routes tickets, makes the call', color: 'var(--a-boss)' },
  { id: 'inventory', name: 'Inventory', short: 'IN', role: 'Stock, sizes, vendors, ETAs', color: 'var(--a-inventory)' },
  { id: 'accounting', name: 'Accounting', short: 'AC', role: 'Cash, invoices, margins, approvals', color: 'var(--a-accounting)' },
  { id: 'facilities', name: 'Facilities', short: 'FA', role: 'Lease, rent, shop space', color: 'var(--a-facilities)' },
  { id: 'customer_service', name: 'Customer Service', short: 'CS', role: 'Customer drafts', color: 'var(--a-cs)' },
]

export const AGENT_BY_ID = Object.fromEntries(AGENTS.map((a) => [a.id, a])) as Record<AgentId, AgentMeta>

export const isAgent = (x: string | null | undefined): x is AgentId => !!x && x in AGENT_BY_ID

const GLYPHS: Record<AgentId, React.ReactNode> = {
  // crown
  boss: <path d="M3 18 4.6 8l4.6 4.2L12 5l2.8 7.2L19.4 8 21 18Z" />,
  // shipping box
  inventory: (
    <>
      <path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5Z" />
      <path d="M3.5 7.5 12 12l8.5-4.5M12 12v9" fill="none" strokeWidth="1.6" stroke="var(--glyph-cut)" />
    </>
  ),
  // coin with $
  accounting: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path
        d="M14.6 8.6c-.6-.8-1.6-1.2-2.7-1.2-1.6 0-2.7.8-2.7 2 0 2.8 5.6 1.4 5.6 4.3 0 1.2-1.2 2.1-2.9 2.1-1.2 0-2.3-.5-2.9-1.4M12 5.8v12.4"
        fill="none"
        stroke="var(--glyph-cut)"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </>
  ),
  // storefront
  facilities: (
    <>
      <path d="M3 10 5 4h14l2 6v10H3Z" />
      <path d="M9.5 20v-6h5v6M3 10h18" fill="none" stroke="var(--glyph-cut)" strokeWidth="1.6" />
    </>
  ),
  // speech bubble
  customer_service: (
    <>
      <path d="M4 4.5h16a1 1 0 0 1 1 1V16a1 1 0 0 1-1 1H10l-5 4v-4H4a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1Z" />
      <path d="M7.5 9.5h9M7.5 12.5h6" fill="none" stroke="var(--glyph-cut)" strokeWidth="1.6" strokeLinecap="round" />
    </>
  ),
}

export function AgentGlyph({ id, size = 22 }: { id: AgentId; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
      {GLYPHS[id]}
    </svg>
  )
}

export function AgentBadge({ id, compact = false }: { id: string | null | undefined; compact?: boolean }) {
  if (!isAgent(id)) {
    const label = id === 'human' ? 'You' : id ?? 'System'
    return <span className={`badge badge-human${compact ? ' compact' : ''}`}>{label}</span>
  }
  const a = AGENT_BY_ID[id]
  return (
    <span className={`badge${compact ? ' compact' : ''}`} style={{ '--agent': a.color } as React.CSSProperties}>
      <AgentGlyph id={id} size={compact ? 13 : 15} />
      {compact ? a.short : a.name}
    </span>
  )
}
