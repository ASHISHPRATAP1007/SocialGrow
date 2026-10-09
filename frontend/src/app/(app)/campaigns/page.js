'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2, Minus } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Bar, EmptyState, Field, Loading, PLATFORMS, P_LABEL, PageHeader, Panel, PlatformBadge, addDays, can, errMsg, inr, niceDate, selectClass, today, useMe } from '@/components/sg'

const STATUS_CLASS = { planned: 'bg-secondary text-secondary-foreground', active: 'bg-success-soft text-success', completed: 'bg-muted text-muted-foreground' }

export default function CampaignsPage() {
  const me = useMe()
  const allowed = me.limits.campaigns
  const { data: campaigns } = useApi(allowed ? '/campaigns' : null)
  const { data: clients } = useApi(allowed ? '/clients' : null)
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ clientId: '', name: '', platform: 'instagram', goal: 'Engagement', startDate: today(), endDate: addDays(today(), 30), budget: '10000', contentPlanned: '20' })
  const manage = can(me.role, 'manage')
  const content = can(me.role, 'content')

  if (!allowed) {
    return (
      <>
        <PageHeader title="Campaigns" />
        <EmptyState title="Pro plan feature" text="Campaign management Pro aur Agency plans mein available hai." action={<ButtonLink href="/billing">Upgrade</ButtonLink>} />
      </>
    )
  }
  if (!campaigns || !clients) return <Loading />

  const act = (p, ok) =>
    p.then(() => {
      if (ok) toast.success(ok)
      refreshAll()
    }).catch((e) => toast.error(errMsg(e)))

  return (
    <>
      <PageHeader title="Campaigns" subtitle="Client campaigns, goals aur content progress" actions={manage && <Button onClick={() => setOpen((o) => !o)} disabled={!clients.length}><Plus className="size-4" /> New campaign</Button>} />
      {open && (
        <Panel title="New campaign" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              act(
                api.post('/campaigns', { ...f, budget: Number(f.budget) || 0, contentPlanned: Number(f.contentPlanned) || 0 }).then(() => setOpen(false)),
                'Campaign ban gaya',
              )
            }}
          >
            <Field label="Campaign name"><Input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Client">
              <select className={selectClass} required value={f.clientId} onChange={(e) => setF({ ...f, clientId: e.target.value })}>
                <option value="">Select</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Platform">
              <select className={selectClass} value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>
                {PLATFORMS.map((p) => <option key={p} value={p}>{P_LABEL[p]}</option>)}
              </select>
            </Field>
            <Field label="Goal">
              <select className={selectClass} value={f.goal} onChange={(e) => setF({ ...f, goal: e.target.value })}>
                {['Engagement', 'Awareness', 'Followers', 'Leads', 'Website traffic'].map((g) => <option key={g}>{g}</option>)}
              </select>
            </Field>
            <Field label="Start"><Input type="date" value={f.startDate} onChange={(e) => setF({ ...f, startDate: e.target.value })} /></Field>
            <Field label="End"><Input type="date" value={f.endDate} onChange={(e) => setF({ ...f, endDate: e.target.value })} /></Field>
            <Field label="Budget (₹)"><Input type="number" min={0} value={f.budget} onChange={(e) => setF({ ...f, budget: e.target.value })} /></Field>
            <Field label="Planned content pieces"><Input type="number" min={0} value={f.contentPlanned} onChange={(e) => setF({ ...f, contentPlanned: e.target.value })} /></Field>
            <div className="flex gap-2"><Button type="submit">Create</Button><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
          </form>
        </Panel>
      )}
      {campaigns.length === 0 ? (
        <EmptyState title="Koi campaign nahi" text="Ek campaign banayein aur uska content progress track karein." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {campaigns.map((c) => (
            <div key={c.id} className="rounded-xl border bg-card p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div className="text-xs text-muted-foreground">{c.clientName} · {niceDate(c.startDate)} – {niceDate(c.endDate)}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold capitalize ${STATUS_CLASS[c.status]}`}>{c.status}</span>
                  {manage && (
                    <button aria-label="Delete campaign" className="text-muted-foreground hover:text-destructive" onClick={() => confirm('Campaign delete karein?') && act(api.delete(`/campaigns/${c.id}`))}>
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-4 gap-2 text-center text-sm">
                <div><div className="text-[11px] text-muted-foreground">Goal</div><div className="font-semibold">{c.goal}</div></div>
                <div><div className="text-[11px] text-muted-foreground">Budget</div><div className="font-semibold">{inr(c.budget)}</div></div>
                <div><div className="text-[11px] text-muted-foreground">Avg engagement</div><div className="font-semibold">{c.engagementRate.toFixed(1)}%</div></div>
                <div className="flex flex-col items-center"><div className="text-[11px] text-muted-foreground">Platform</div><PlatformBadge platform={c.platform} label={false} /></div>
              </div>
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-xs">
                  <span>Content published</span>
                  <span className="font-semibold">{c.contentPublished} / {c.contentPlanned} ({c.progress.toFixed(0)}%)</span>
                </div>
                <div className="flex items-center gap-2">
                  {content && <button aria-label="Decrease" className="rounded border p-0.5" onClick={() => act(api.patch(`/campaigns/${c.id}/progress`, { delta: -1 }))}><Minus className="size-3" /></button>}
                  <Bar value={c.progress} />
                  {content && <button aria-label="Increase" className="rounded border p-0.5" onClick={() => act(api.patch(`/campaigns/${c.id}/progress`, { delta: 1 }))}><Plus className="size-3" /></button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
