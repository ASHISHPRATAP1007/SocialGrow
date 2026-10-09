'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Check, X, Clock, IndianRupee, Settings2 } from 'lucide-react'
import { Bar as RBar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, Field, Loading, PageHeader, Panel, Stat, errMsg, inr, selectClass, useMe } from '@/components/sg'
import { GatewayPanel } from '@/components/gateway-panel'

const STATE_CLS = {
  pending: 'bg-warning-soft text-warning',
  trial: 'bg-secondary text-secondary-foreground',
  active: 'bg-success-soft text-success',
  grace: 'bg-warning-soft text-warning',
  expired: 'bg-danger-soft text-destructive',
  rejected: 'bg-danger-soft text-destructive',
  suspended: 'bg-danger-soft text-destructive',
}

function run(p, ok) {
  p.then(() => {
    toast.success(ok)
    refreshAll()
  }).catch((e) => toast.error(errMsg(e)))
}

export default function AdminPage() {
  const me = useMe()
  const { data: stats, error } = useApi(me.isPlatformAdmin ? '/admin/stats' : null)
  const [s, setS] = useState({ upiId: '', payeeName: '', supportPhone: '', trialDays: '30' })
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (stats && !loaded) {
      setS({ ...stats.settings, trialDays: String(stats.settings.trialDays) })
      setLoaded(true)
    }
  }, [stats, loaded])

  if (!me.isPlatformAdmin || error) return <EmptyState title="Access denied" text="Ye page sirf platform admins ke liye hai." />
  if (!stats) return <Loading />
  const t = stats.totals

  return (
    <>
      <PageHeader title="Admin Panel" subtitle="Approvals, payments aur poore platform ka business overview" />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="MRR" value={inr(t.mrr)} />
        <Stat label="Revenue (month)" value={inr(t.revenueThisMonth)} />
        <Stat label="Paying agencies" value={String(t.paidAgencies)} />
        <Stat label="On trial" value={String(t.trials)} />
        <Stat label="Pending approval" value={String(t.pending)} />
        <Stat label="Expired" value={String(t.expired)} />
        <Stat label="Users" value={String(t.users)} hint={`${t.activeUsers} active (30d)`} />
        <Stat label="Clients" value={String(t.clients)} />
        <Stat label="Projects" value={String(t.projects)} />
        <Stat label="Social accounts" value={String(t.accounts)} />
        <Stat label="AI requests (month)" value={String(t.aiRequests)} />
        <Stat label="Agencies" value={String(t.agencies)} />
      </div>

      {stats.pendingAgencies.length > 0 && (
        <Panel className="mt-4" title={<span className="flex items-center gap-2"><Clock className="size-4 text-warning" /> Pending approvals ({stats.pendingAgencies.length})</span>}>
          <div className="divide-y">
            {stats.pendingAgencies.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <div className="font-semibold">{a.name}</div>
                  <div className="text-xs text-muted-foreground">{a.owner} {a.phone && `· 📞 ${a.phone}`} · {new Date(a.createdAt).toLocaleString('en-IN')}</div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => run(api.post(`/admin/agencies/${a.id}/approve`), `${a.name} approved — trial shuru`)}><Check className="size-4" /> Approve + start trial</Button>
                  <Button size="sm" variant="ghost" onClick={() => confirm(`${a.name} ko reject karein?`) && run(api.post(`/admin/agencies/${a.id}/reject`), 'Rejected')}><X className="size-4" /> Reject</Button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel className="mt-4" title={<span className="flex items-center gap-2"><IndianRupee className="size-4 text-success" /> UPI payments to verify ({stats.pendingPayments.length})</span>}>
        {stats.pendingPayments.length === 0 ? (
          <p className="text-sm text-muted-foreground">Koi payment verify karna baaki nahi. (Razorpay payments apne aap verify hote hain.)</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-muted-foreground">Apne bank / UPI app mein UTR aur amount match karke hi Verify dabayein.</p>
            <div className="divide-y">
              {stats.pendingPayments.map((p) => (
                <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="text-sm">
                    <div className="font-semibold">{p.agency} — {inr(p.amount)}</div>
                    <div className="text-xs text-muted-foreground">
                      UTR <b className="font-mono">{p.reference}</b> · {p.plan} · {p.months ?? 1} month(s) · {p.owner} · {new Date(p.createdAt).toLocaleString('en-IN')}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => run(api.post(`/admin/payments/${p.id}/verify`), 'Payment verified — plan active')}><Check className="size-4" /> Verify</Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        const note = prompt('Reject ka reason (agency ko dikhega):', 'UTR match nahi hua')
                        if (note !== null) run(api.post(`/admin/payments/${p.id}/reject`, { note }), 'Payment rejected')
                      }}
                    >
                      <X className="size-4" /> Reject
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>

      <GatewayPanel />

      <Panel className="mt-4" title={<span className="flex items-center gap-2"><Settings2 className="size-4" /> Trial & UPI fallback settings</span>}>
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault()
            run(api.put('/admin/settings', { ...s, trialDays: Number(s.trialDays) }), 'Settings saved')
          }}
        >
          <Field label="UPI ID (paisa yahan aayega)"><Input value={s.upiId} onChange={(e) => setS({ ...s, upiId: e.target.value })} placeholder="yourname@okhdfcbank" /></Field>
          <Field label="Payee name"><Input value={s.payeeName} onChange={(e) => setS({ ...s, payeeName: e.target.value })} placeholder="Ashish Pratap" /></Field>
          <Field label="Support phone"><Input value={s.supportPhone} onChange={(e) => setS({ ...s, supportPhone: e.target.value })} placeholder="98765 43210" /></Field>
          <Field label="Free trial (days)"><Input type="number" min={1} max={90} value={s.trialDays} onChange={(e) => setS({ ...s, trialDays: e.target.value })} /></Field>
          <div className="flex items-end"><Button type="submit">Save</Button></div>
        </form>
      </Panel>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_2fr]">
        <Panel title="Paying plan mix">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.planMix}>
                <XAxis dataKey="plan" fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} width={28} />
                <Tooltip />
                <RBar dataKey="count" fill="var(--color-chart-1)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Recent payments">
          {stats.payments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No payments yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground uppercase"><tr><th className="py-2">Invoice</th><th>Agency</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th></tr></thead>
                <tbody>
                  {stats.payments.map((p) => (
                    <tr key={p.id} className="border-t">
                      <td className="py-2 font-mono text-xs">{p.invoiceNo}</td><td>{p.agency}</td><td className="capitalize">{p.plan}</td><td>{inr(p.amount)}</td>
                      <td className="text-xs">{p.method ?? '—'}</td><td className="text-xs uppercase">{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="All agencies" className="mt-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground uppercase">
              <tr><th className="py-2">Agency</th><th>Owner</th><th>Status</th><th>Ends</th><th>Billing</th><th>Clients</th><th>Accounts</th><th>AI</th><th>Plan</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {stats.agencies.map((a) => (
                <tr key={a.id} className="border-t align-middle">
                  <td className="py-2 font-medium">{a.name}</td>
                  <td className="text-xs">{a.owner}{a.phone && <div className="text-muted-foreground">{a.phone}</div>}</td>
                  <td><span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${STATE_CLS[a.access.state]}`}>{a.access.state}</span></td>
                  <td className="text-xs whitespace-nowrap">{a.access.endsAt ? `${new Date(a.access.endsAt).toLocaleDateString('en-IN')}${a.access.daysLeft ? ` (${a.access.daysLeft}d)` : ''}` : '—'}</td>
                  <td className="text-xs">{a.autoRenew ? `🔁 ${a.billingCycle}` : '—'}</td>
                  <td>{a.clients}</td>
                  <td>{a.accounts}</td>
                  <td>{a.aiThisMonth}</td>
                  <td>
                    <select className={selectClass + ' h-8 w-24'} value={a.plan} onChange={(e) => run(api.post(`/admin/agencies/${a.id}/plan`, { plan: e.target.value }), 'Plan updated')}>
                      {['starter', 'pro', 'agency', 'free'].map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </td>
                  <td className="whitespace-nowrap">
                    <div className="flex gap-1">
                      {!['pending', 'rejected'].includes(a.access.state) && (
                        <Button size="sm" variant="ghost" title="7 din add karein" onClick={() => run(api.post(`/admin/agencies/${a.id}/extend`, { days: 7 }), '7 din add kiye')}>+7d</Button>
                      )}
                      {['suspended', 'rejected'].includes(a.access.state) ? (
                        <Button size="sm" variant="ghost" onClick={() => run(api.post(`/admin/agencies/${a.id}/status`, { status: 'active' }), 'Activated')}>Activate</Button>
                      ) : a.access.state !== 'pending' && a.id !== me.agency.id ? (
                        <Button size="sm" variant="ghost" className="text-destructive" onClick={() => confirm('Agency suspend karein?') && run(api.post(`/admin/agencies/${a.id}/status`, { status: 'suspended' }), 'Suspended')}>Suspend</Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  )
}
