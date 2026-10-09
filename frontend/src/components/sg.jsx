'use client'

import { createContext, useContext } from 'react'
import { Instagram, Facebook, Youtube, TrendingUp, TrendingDown, Loader2, Radio } from 'lucide-react'
import { cn } from '@/lib/utils'

export const MeContext = createContext(null)
export function useMe() {
  const me = useContext(MeContext)
  if (!me) throw new Error('useMe outside app shell')
  return me
}

export const PLATFORMS = ['instagram', 'facebook', 'youtube']

export const ROLE_LABEL = {
  owner: 'Owner',
  admin: 'Admin',
  manager: 'Manager',
  analyst: 'Analyst',
  content_manager: 'Content Manager',
  viewer: 'Viewer',
}

export function can(role, action) {
  const map = {
    manage: ['owner', 'admin', 'manager'],
    content: ['owner', 'admin', 'manager', 'content_manager'],
    reports: ['owner', 'admin', 'manager', 'analyst'],
    admin: ['owner', 'admin'],
    owner: ['owner'],
  }
  return map[action].includes(role)
}

/** Readable message from an API (axios) error. */
export function errMsg(e) {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail.slice(0, 220)
  if (Array.isArray(detail) && detail[0]?.msg) return `Form check karein: ${detail[0].msg}`.slice(0, 220)
  if (e?.code === 'ERR_NETWORK') return 'Server se connect nahi ho paya. Internet / backend URL check karein.'
  return (e?.message || String(e)).slice(0, 220)
}

export function fmt(n) {
  if (Math.abs(n) >= 10_000_000) return (n / 10_000_000).toFixed(1) + 'Cr'
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (Math.abs(n) >= 10_000) return (n / 1000).toFixed(1) + 'K'
  return Math.round(n).toLocaleString('en-IN')
}
export const inr = (n) => '₹' + Number(n).toLocaleString('en-IN')
export const today = () => new Date().toISOString().slice(0, 10)
export function addDays(date, n) {
  const d = new Date(date + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}
export function niceDate(d) {
  return new Date(d + 'T00:00:00Z').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

const P_ICON = { instagram: Instagram, facebook: Facebook, youtube: Youtube }
const P_CLASS = { instagram: 'text-instagram bg-instagram/10', facebook: 'text-facebook bg-facebook/10', youtube: 'text-youtube bg-youtube/10' }
export const P_LABEL = { instagram: 'Instagram', facebook: 'Facebook', youtube: 'YouTube' }

export function PlatformBadge({ platform, label = true }) {
  const Icon = P_ICON[platform]
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold', P_CLASS[platform])}>
      <Icon className="size-3.5" />
      {label && P_LABEL[platform]}
    </span>
  )
}

export function DemoBadge() {
  return (
    <span title="Sample data — real data aane ke liye platform API connect karein" className="rounded-full bg-warning-soft px-2 py-0.5 text-[10px] font-bold tracking-wide text-warning uppercase">
      Demo data
    </span>
  )
}

export function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-[10px] font-bold tracking-wide text-success uppercase">
      <Radio className="size-3" /> Live data
    </span>
  )
}

export function SourceBadges({ demo, live }) {
  if (!demo && !live) return null
  return (
    <span className="flex gap-1.5">
      {live && <LiveBadge />}
      {demo && <DemoBadge />}
    </span>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Panel({ title, action, children, className }) {
  return (
    <section className={cn('rounded-xl border bg-card p-5 shadow-sm', className)}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title && <h2 className="font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Delta({ value }) {
  if (value === null || value === undefined) return null
  const up = value >= 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-semibold', up ? 'text-success' : 'text-destructive')}>
      <Icon className="size-3.5" />
      {up ? '+' : ''}
      {value.toFixed(1)}%
    </span>
  )
}

export function Stat({ label, value, delta, hint }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className="mt-2 text-2xl font-bold tracking-tight">{value}</div>
      <div className="mt-1 flex items-center gap-2">
        <Delta value={delta} />
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </div>
    </div>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  )
}

export function EmptyState({ title, text, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed bg-card px-6 py-14 text-center">
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{text}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Field({ label, children, hint }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  )
}

export const selectClass =
  'h-9 w-full rounded-md border border-input bg-card px-3 text-sm shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/40'

export function Bar({ value, className }) {
  return (
    <div className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}>
      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

/** Tiny markdown renderer for AI output (headings, bullets, numbered lists, bold, `code`). */
export function Markdownish({ text }) {
  const lines = text.split('\n')
  const out = []
  let list = null
  const inline = (s) =>
    s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : part.startsWith('`') && part.endsWith('`') && part.length > 1 ? (
        <code key={i} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">{part.slice(1, -1)}</code>
      ) : (
        <span key={i}>{part}</span>
      ),
    )
  const flush = () => {
    if (!list) return
    const Tag = list.ordered ? 'ol' : 'ul'
    out.push(
      <Tag key={out.length} className={cn('my-2 space-y-1 pl-5 text-sm', list.ordered ? 'list-decimal' : 'list-disc')}>
        {list.items.map((it, i) => (
          <li key={i}>{inline(it)}</li>
        ))}
      </Tag>,
    )
    list = null
  }
  for (const raw of lines) {
    const line = raw.trim()
    if (!line || /^[-*_]{3,}$/.test(line)) {
      flush()
      continue
    }
    const h = line.match(/^#{1,4}\s+(.*)/)
    const b = line.match(/^(?:[-*•])\s+(.*)/)
    const n = line.match(/^\d+[.)]\s+(.*)/)
    if (h) {
      flush()
      out.push(
        <h4 key={out.length} className="mt-4 mb-1 text-sm font-bold first:mt-0">
          {h[1]}
        </h4>,
      )
    } else if (b || n) {
      const ordered = !!n
      if (!list || list.ordered !== ordered) {
        flush()
        list = { ordered, items: [] }
      }
      list.items.push((b || n)[1])
    } else {
      flush()
      out.push(
        <p key={out.length} className="my-1.5 text-sm leading-relaxed">
          {inline(line)}
        </p>,
      )
    }
  }
  flush()
  return <div>{out}</div>
}
