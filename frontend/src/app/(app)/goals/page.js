'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Bar, EmptyState, Field, Loading, P_LABEL, PageHeader, Panel, can, errMsg, fmt, niceDate, selectClass, useMe } from '@/components/sg'

export default function GoalsPage() {
  const me = useMe()
  const { data: goals } = useApi('/goals')
  const { data: accounts } = useApi('/accounts')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ accountId: '', target: '', days: '30' })
  const manage = can(me.role, 'manage')

  if (!goals || !accounts) return <Loading />

  return (
    <>
      <PageHeader
        title="Growth Goals"
        subtitle="Follower targets set karein aur progress track karein"
        actions={manage && accounts.length > 0 && <Button onClick={() => setOpen((o) => !o)}><Plus className="size-4" /> New goal</Button>}
      />
      {open && (
        <Panel title="New goal" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-4"
            onSubmit={async (e) => {
              e.preventDefault()
              try {
                await api.post('/goals', { accountId: form.accountId, target: Number(form.target), days: Number(form.days) })
                toast.success('Goal set ho gaya')
                setOpen(false)
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              }
            }}
          >
            <Field label="Account">
              <select className={selectClass} required value={form.accountId} onChange={(e) => setForm({ ...form, accountId: e.target.value })}>
                <option value="">Select</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{P_LABEL[a.platform]} · @{a.username}</option>)}
              </select>
            </Field>
            <Field label="Target followers">
              <Input type="number" required min={1} value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} placeholder="15000" />
            </Field>
            <Field label="Period (days)">
              <Input type="number" min={7} max={365} value={form.days} onChange={(e) => setForm({ ...form, days: e.target.value })} />
            </Field>
            <div className="flex items-end"><Button type="submit">Save goal</Button></div>
          </form>
          <p className="mt-2 text-xs text-muted-foreground">Goal ka start 14 din pehle se count hota hai taaki existing history se progress turant dikhe.</p>
        </Panel>
      )}
      {goals.length === 0 ? (
        <EmptyState title="Koi goal nahi" text="Example: Current 10,000 → Target 15,000 in 30 days." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {goals.map((g) => (
            <Panel
              key={g.id}
              title={g.account}
              action={
                manage && (
                  <button
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete goal"
                    onClick={() => api.delete(`/goals/${g.id}`).then(refreshAll).catch((e) => toast.error(errMsg(e)))}
                  >
                    <Trash2 className="size-4" />
                  </button>
                )
              }
            >
              <div className="grid grid-cols-4 gap-2 text-center">
                <div><div className="text-lg font-bold">{fmt(g.startValue)}</div><div className="text-[11px] text-muted-foreground">Start</div></div>
                <div><div className="text-lg font-bold">{fmt(g.current)}</div><div className="text-[11px] text-muted-foreground">Current</div></div>
                <div><div className="text-lg font-bold">{fmt(g.target)}</div><div className="text-[11px] text-muted-foreground">Target</div></div>
                <div><div className="text-lg font-bold text-success">+{fmt(g.gained)}</div><div className="text-[11px] text-muted-foreground">Growth</div></div>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <Bar value={g.progress} />
                <span className="text-sm font-bold">{g.progress.toFixed(0)}%</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{niceDate(g.startDate)} → {niceDate(g.endDate)}</div>
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={g.history}>
                    <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={10} />
                    <YAxis domain={['auto', g.target]} tickFormatter={(v) => fmt(v)} fontSize={10} width={44} />
                    <Tooltip formatter={(v) => fmt(Number(v))} />
                    <ReferenceLine y={g.target} stroke="var(--color-success)" strokeDasharray="4 4" />
                    <Line dataKey="followers" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}
