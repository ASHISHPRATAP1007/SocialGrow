'use client'

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Check, X, Smartphone, Copy, ShieldCheck, RefreshCw, Repeat, CreditCard } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Bar, Field, Loading, PageHeader, Panel, can, errMsg, inr, useMe } from '@/components/sg'

const PAID = ['starter', 'pro', 'agency']
const STATE_LABEL = {
  trial: { text: 'Free trial', cls: 'bg-secondary text-secondary-foreground' },
  active: { text: 'Active', cls: 'bg-success-soft text-success' },
  grace: { text: 'Payment due', cls: 'bg-warning-soft text-warning' },
  expired: { text: 'Expired — read-only', cls: 'bg-danger-soft text-destructive' },
}
const PAY_STATUS = {
  pending: 'bg-warning-soft text-warning',
  paid: 'bg-success-soft text-success',
  rejected: 'bg-danger-soft text-destructive',
  test: 'bg-muted text-muted-foreground',
}

export default function BillingPage() {
  const me = useMe()
  const { data: plans } = useApi('/billing/plans')
  const { data: info } = useApi('/billing/payment-info')
  const { data: invoices } = useApi('/billing/invoices')
  const { data: gw } = useApi('/billing/gateway-ready')
  const { data: clients } = useApi('/clients')
  const { data: projects } = useApi('/projects')
  const { data: members } = useApi('/members')
  const [cycle, setCycle] = useState('yearly')
  const [busy, setBusy] = useState(null)
  const [upiPlan, setUpiPlan] = useState(null)
  const [utr, setUtr] = useState('')
  const owner = can(me.role, 'owner')
  const awaitingReturn = useRef(false)

  // When the owner comes back from the Razorpay tab, pull the latest status automatically
  useEffect(() => {
    const onFocus = () => {
      if (awaitingReturn.current && owner) {
        awaitingReturn.current = false
        api.post('/billing/sync').then(refreshAll).catch(() => undefined)
      }
    }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [owner])

  if (!plans || !info || !invoices || !gw) return <Loading />

  const gateway = gw.ready
  const a = me.access
  const ag = me.agency
  const st = STATE_LABEL[a.state] ?? STATE_LABEL.active
  const subStatus = ag.razorpaySubStatus
  const autoRenewOn = ag.hasRazorpaySubscription && ['active', 'authenticated', 'pending', 'halted'].includes(subStatus ?? '') && !ag.cancelAtPeriodEnd
  const awaitingPay = ag.hasRazorpaySubscription && subStatus === 'created'
  const pendingUpi = invoices.find((i) => i.status === 'pending')
  const [pPlan, pCycle] = (ag.pendingPlan ?? '').split(':')

  const usage = [
    ['Clients', clients?.length ?? 0, me.limits.clients],
    ['Projects', projects?.length ?? 0, me.limits.projects],
    ['Team seats', members?.length ?? 0, me.limits.members],
    ['AI requests (this month)', me.aiUsed, me.limits.aiPerMonth],
  ]

  async function doSubscribe(plan) {
    setBusy(plan)
    try {
      const { data } = await api.post('/billing/subscribe', { plan, cycle })
      awaitingReturn.current = true
      window.open(data.url, '_blank', 'noopener')
      toast.success('Razorpay payment page khul gaya. Payment ke baad yahan wapas aayein.')
      refreshAll()
    } catch (e) {
      toast.error(errMsg(e))
    } finally {
      setBusy(null)
    }
  }

  const upiAmount = upiPlan ? (cycle === 'yearly' ? plans[upiPlan].yearlyPrice : plans[upiPlan].price) : 0
  const upiLink =
    upiPlan && info.upiId
      ? `upi://pay?pa=${encodeURIComponent(info.upiId)}&pn=${encodeURIComponent(info.payeeName)}&am=${upiAmount}&cu=INR&tn=${encodeURIComponent(`SocialGrow ${plans[upiPlan].label}`)}`
      : ''

  return (
    <>
      <PageHeader title="Billing & Subscription" subtitle="Plan chunein — auto-renew ke saath, koi tension nahi." />

      <Panel className="mb-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase">Current plan</div>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-2xl font-extrabold">{me.limits.label}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${st.cls}`}>{st.text}</span>
              {ag.billingCycle && a.state !== 'trial' && <span className="text-xs text-muted-foreground capitalize">· {ag.billingCycle}</span>}
            </div>
            {a.endsAt && (
              <div className="mt-1 text-sm text-muted-foreground">
                {a.state === 'trial' ? 'Trial khatam' : a.state === 'expired' ? 'Khatam hua' : autoRenewOn ? 'Next auto-charge' : 'Plan valid till'}:{' '}
                <b>{new Date(a.endsAt).toLocaleDateString('en-IN')}</b>
                {a.daysLeft > 0 && ` (${a.daysLeft} din)`}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${autoRenewOn ? 'bg-success-soft text-success' : 'bg-muted text-muted-foreground'}`}>
              <Repeat className="size-3.5" /> Auto-renew {autoRenewOn ? 'ON' : 'OFF'}
            </span>
            {autoRenewOn && pPlan && a.state === 'trial' && (
              <span className="text-xs text-muted-foreground">Trial ke baad: {plans[pPlan]?.label} ({pCycle}) apne aap shuru</span>
            )}
            {subStatus === 'halted' && <span className="text-xs font-semibold text-destructive">Payments fail ho rahe hain — dobara subscribe karein</span>}
            {owner && gateway && ag.hasRazorpaySubscription && (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy !== null}
                  onClick={async () => {
                    setBusy('sync')
                    try {
                      const { data } = await api.post('/billing/sync')
                      toast.success(`Status: ${data.status}`)
                      refreshAll()
                    } catch (e) {
                      toast.error(errMsg(e))
                    } finally {
                      setBusy(null)
                    }
                  }}
                >
                  <RefreshCw className={`size-3.5 ${busy === 'sync' ? 'animate-spin' : ''}`} /> Refresh status
                </Button>
                {autoRenewOn && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive"
                    disabled={busy !== null}
                    onClick={async () => {
                      if (!confirm('Auto-renew band karein? Plan current period end tak chalega.')) return
                      setBusy('cancel')
                      try {
                        await api.post('/billing/cancel')
                        toast.success('Auto-renew band ho gaya')
                        refreshAll()
                      } catch (e) {
                        toast.error(errMsg(e))
                      } finally {
                        setBusy(null)
                      }
                    }}
                  >
                    Cancel auto-renew
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
        {awaitingPay && (
          <div className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
            Payment page khula tha par abhi tak complete nahi hua. Payment ke baad <b>Refresh status</b> dabayein, ya plan dobara chunein.
          </div>
        )}
      </Panel>

      <Panel title="Usage" className="mb-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {usage.map(([label, used, limit]) => (
            <div key={label}>
              <div className="mb-1 flex justify-between text-xs"><span>{label}</span><span className="font-semibold">{used} / {limit >= 1000 ? '∞' : limit}</span></div>
              <Bar value={(used / limit) * 100} />
            </div>
          ))}
        </div>
      </Panel>

      <div className="mb-4 flex justify-center">
        <div className="inline-flex rounded-full border bg-card p-1">
          {['monthly', 'yearly'].map((c) => (
            <button key={c} onClick={() => setCycle(c)} className={`rounded-full px-4 py-1.5 text-sm font-semibold ${cycle === c ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>
              {c === 'monthly' ? 'Monthly' : 'Yearly'}
              {c === 'yearly' && <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] ${cycle === c ? 'bg-primary-foreground/20' : 'bg-success-soft text-success'}`}>2 mahine FREE</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {PAID.map((k) => {
          const p = plans[k]
          const perMonth = cycle === 'yearly' ? Math.round(p.yearlyPrice / 12) : p.price
          const isCurrent = ag.plan === k && autoRenewOn && (ag.billingCycle ?? pCycle) === cycle
          const feats = [
            [`${p.clients >= 1000 ? 'Unlimited*' : p.clients} clients, ${p.projects >= 5000 ? 'unlimited*' : p.projects} projects`, true],
            [`${p.members} team seats`, true],
            [`${p.aiPerMonth} AI requests / month`, true],
            ['Real Instagram, Facebook, YouTube data', true],
            ['Client reports (PDF)', p.reports],
            ['AI Analyst + AI Content + Calendar', p.aiContent],
            ['Campaigns', p.campaigns],
            ['White label (aapka brand)', p.whiteLabel],
          ]
          return (
            <div key={k} className={`relative flex flex-col rounded-xl border bg-card p-5 shadow-sm ${k === 'pro' ? 'border-primary ring-2 ring-primary/20' : ''}`}>
              {k === 'pro' && <span className="absolute -top-2.5 right-4 rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-primary-foreground">POPULAR</span>}
              <div className="text-sm font-bold tracking-wide uppercase">{p.label}</div>
              <div className="mt-2 text-3xl font-extrabold">
                {inr(perMonth)}
                <span className="text-sm font-medium text-muted-foreground">/mo</span>
              </div>
              <div className="text-xs text-muted-foreground">
                {cycle === 'yearly' ? (
                  <><b className="text-success">{inr(p.yearlyPrice)}/year</b> · <span className="line-through">{inr(p.price * 12)}</span></>
                ) : (
                  'Billed monthly'
                )}
              </div>
              <ul className="mt-4 flex-1 space-y-2 text-sm">
                {feats.map(([t, ok]) => (
                  <li key={t} className={`flex items-start gap-2 ${ok ? '' : 'text-muted-foreground line-through'}`}>
                    {ok ? <Check className="mt-0.5 size-4 shrink-0 text-success" /> : <X className="mt-0.5 size-4 shrink-0" />} {t}
                  </li>
                ))}
              </ul>
              {gateway ? (
                <Button className="mt-5" variant={k === 'pro' ? 'default' : 'outline'} disabled={!owner || busy !== null || isCurrent || autoRenewOn} onClick={() => doSubscribe(k)}>
                  <CreditCard className="size-4" />
                  {!owner ? 'Owner only' : isCurrent ? 'Current plan' : autoRenewOn ? 'Pehle auto-renew cancel karein' : busy === k ? 'Opening…' : a.state === 'trial' ? 'Subscribe (trial ke baad charge)' : 'Subscribe'}
                </Button>
              ) : (
                <Button className="mt-5" variant="outline" disabled={!owner || !!pendingUpi || !info.upiId} onClick={() => setUpiPlan(k)}>
                  {!owner ? 'Owner only' : pendingUpi ? 'Verification pending' : !info.upiId ? 'Payment jaldi available' : 'Pay via UPI'}
                </Button>
              )}
            </div>
          )
        })}
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        {gateway ? 'Secure payment by Razorpay — Card, UPI Autopay, Netbanking. Kabhi bhi cancel karein.' : '* Fair-use limits apply.'}
      </p>

      {!gateway && upiPlan && owner && !pendingUpi && info.upiId && (
        <Panel className="mt-4 border-primary/40" title={<span className="flex items-center gap-2"><Smartphone className="size-4 text-primary" /> Pay {inr(upiAmount)} via UPI — {plans[upiPlan].label} ({cycle})</span>}>
          <div className="grid gap-6 md:grid-cols-[220px_1fr]">
            <div className="flex flex-col items-center gap-2">
              <div className="rounded-xl border bg-white p-3"><QRCodeSVG value={upiLink} size={180} /></div>
              <a href={upiLink} className="text-xs font-semibold text-primary underline md:hidden">UPI app kholein</a>
            </div>
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2 rounded-lg bg-muted/60 p-3 text-sm">
                <span className="text-muted-foreground">UPI ID:</span> <b className="font-mono">{info.upiId}</b>
                <button aria-label="Copy UPI ID" onClick={() => { void navigator.clipboard.writeText(info.upiId); toast.success('Copied') }}><Copy className="size-3.5" /></button>
              </div>
              <form
                className="flex flex-col gap-2 sm:flex-row sm:items-end"
                onSubmit={async (e) => {
                  e.preventDefault()
                  try {
                    await api.post('/billing/upi', { plan: upiPlan, months: cycle === 'yearly' ? 12 : 1, reference: utr })
                    toast.success('Payment submit — verify hone par plan active')
                    setUtr('')
                    setUpiPlan(null)
                    refreshAll()
                  } catch (err) {
                    toast.error(errMsg(err))
                  }
                }}
              >
                <div className="flex-1"><Field label="UTR / Transaction ID"><Input required value={utr} onChange={(e) => setUtr(e.target.value)} placeholder="428615937204" /></Field></div>
                <Button type="submit">Submit</Button>
              </form>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><ShieldCheck className="size-3.5" /> Manual verification — auto-renew ke liye card/UPI Autopay jald aa raha hai.</p>
            </div>
          </div>
        </Panel>
      )}

      <Panel title="Payments & invoices" className="mt-4">
        {invoices.length === 0 ? (
          <p className="text-sm text-muted-foreground">Abhi koi payment nahi.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground uppercase">
                <tr><th className="py-2">Invoice</th><th>Plan</th><th>Period</th><th>Amount</th><th>Method</th><th>Date</th><th>Status</th></tr>
              </thead>
              <tbody>
                {invoices.map((i) => (
                  <tr key={i.id} className="border-t">
                    <td className="py-2 font-mono text-xs">{i.invoiceNo}</td>
                    <td className="capitalize">{i.plan}</td>
                    <td>{i.months === 12 ? 'Yearly' : i.months ? `${i.months} mo` : '—'}</td>
                    <td>{inr(i.amount)}</td>
                    <td className="text-xs">{i.method ?? '—'}</td>
                    <td>{new Date(i.createdAt).toLocaleDateString('en-IN')}</td>
                    <td>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${PAY_STATUS[i.status]}`}>{i.status === 'pending' ? 'verifying' : i.status}</span>
                      {i.note && <div className="text-[11px] text-destructive">{i.note}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  )
}
