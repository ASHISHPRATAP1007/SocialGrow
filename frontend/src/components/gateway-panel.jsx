'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { CreditCard, Copy, CheckCircle2, CircleDashed } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Panel, errMsg } from '@/components/sg'

export function GatewayPanel() {
  const { data: st } = useApi('/admin/gateway')
  const [f, setF] = useState({ keyId: '', keySecret: '', webhookSecret: '' })
  const [busy, setBusy] = useState(false)
  if (!st) return null
  const ready = !!st.keyId
  return (
    <Panel
      className="mt-4"
      title={<span className="flex items-center gap-2"><CreditCard className="size-4 text-primary" /> Razorpay — automatic payments & auto-renew</span>}
      action={
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold ${ready ? 'bg-success-soft text-success' : 'bg-muted text-muted-foreground'}`}>
          {ready ? <CheckCircle2 className="size-3.5" /> : <CircleDashed className="size-3.5" />}
          {ready ? `Connected (${st.mode === 'live' ? 'LIVE' : 'TEST'} mode)` : 'Not connected'}
        </span>
      }
    >
      {ready && (
        <div className="mb-4 grid gap-1 rounded-md bg-muted/50 p-3 text-xs">
          <div>Key ID: <b className="font-mono">{st.keyId}</b></div>
          <div>Webhook secret: <b>{st.hasWebhookSecret ? 'set ✅' : 'missing ⚠️ — webhook kaam nahi karega'}</b></div>
          <div>Razorpay plans created: <b>{st.plansCreated}</b> (pehle subscription pe apne aap bante hain)</div>
        </div>
      )}
      <div className="mb-4 rounded-md border p-3 text-xs">
        <div className="mb-1 font-semibold">Webhook URL (Razorpay Dashboard → Settings → Webhooks mein daalein):</div>
        <div className="flex items-center gap-2">
          <code className="break-all rounded bg-muted px-2 py-1">{st.webhookUrl}</code>
          <button aria-label="Copy webhook URL" onClick={() => { void navigator.clipboard.writeText(st.webhookUrl); toast.success('Copied') }}><Copy className="size-3.5" /></button>
        </div>
        <div className="mt-1 text-muted-foreground">Events tick karein: <b>subscription.*</b> (activated, charged, authenticated, pending, halted, cancelled, completed)</div>
      </div>
      <form
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          try {
            const { data: r } = await api.put('/admin/gateway', f)
            toast.success(`Razorpay connected (${r.mode.toUpperCase()} mode)`)
            setF({ keyId: '', keySecret: '', webhookSecret: '' })
            refreshAll()
          } catch (err) {
            toast.error(errMsg(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <Field label="Key ID"><Input required value={f.keyId} onChange={(e) => setF({ ...f, keyId: e.target.value })} placeholder="rzp_test_..." /></Field>
        <Field label="Key Secret"><Input required type="password" autoComplete="off" value={f.keySecret} onChange={(e) => setF({ ...f, keySecret: e.target.value })} /></Field>
        <Field label="Webhook Secret" hint="Webhook banate waqt jo secret aap likhoge"><Input type="password" autoComplete="off" value={f.webhookSecret} onChange={(e) => setF({ ...f, webhookSecret: e.target.value })} /></Field>
        <div className="flex items-end"><Button type="submit" disabled={busy}>{busy ? 'Checking keys…' : ready ? 'Update keys' : 'Connect Razorpay'}</Button></div>
      </form>
    </Panel>
  )
}
