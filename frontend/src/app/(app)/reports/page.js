'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { FileText, Sparkles } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, Field, Loading, PageHeader, Panel, addDays, can, errMsg, niceDate, selectClass, today, useMe } from '@/components/sg'
import { ClientPicker } from '@/components/client-picker'

const TYPES = { Monthly: 30, Weekly: 7, Campaign: 30, Platform: 30 }

export default function ReportsPage() {
  const me = useMe()
  const router = useRouter()
  const allowed = me.limits.reports
  const { data: reports } = useApi(allowed ? '/reports' : null)
  const { data: clients } = useApi(allowed ? '/clients' : null)
  const [f, setF] = useState({ clientId: '', type: 'Monthly', start: addDays(today(), -29), end: today() })
  const [busy, setBusy] = useState(false)

  if (!allowed) {
    return (
      <>
        <PageHeader title="Client Reports" />
        <EmptyState title="Starter plan feature" text="AI client reports Starter aur upar ke plans mein available hain." action={<ButtonLink href="/billing">Upgrade</ButtonLink>} />
      </>
    )
  }
  if (!reports || !clients) return <Loading />

  return (
    <>
      <PageHeader title="Client Reports" subtitle="AI-written reports, aapke brand ke saath — PDF mein save karein" />
      {can(me.role, 'reports') && (
        <Panel title="Generate report" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!f.clientId) return toast.error('Client chunein')
              setBusy(true)
              try {
                const { data } = await api.post('/reports', f)
                toast.success('Report ready hai')
                refreshAll()
                router.push(`/report-view?id=${data.id}`)
              } catch (err) {
                toast.error(errMsg(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            <Field label="Client">
              <ClientPicker clients={clients} value={f.clientId} onChange={(id) => setF({ ...f, clientId: id })} />
            </Field>
            <Field label="Report type">
              <select
                className={selectClass}
                value={f.type}
                onChange={(e) => {
                  const type = e.target.value
                  setF({ ...f, type, start: addDays(today(), -(TYPES[type] - 1)), end: today() })
                }}
              >
                {Object.keys(TYPES).map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <Field label="From"><Input type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} /></Field>
            <Field label="To"><Input type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} /></Field>
            <div className="flex items-end">
              <Button type="submit" disabled={busy}><Sparkles className="size-4" /> {busy ? 'Generating…' : 'Generate'}</Button>
            </div>
          </form>
        </Panel>
      )}
      {reports.length === 0 ? (
        <EmptyState title="Abhi koi report nahi" text="Upar se client aur period chun kar pehli report banayein." />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-xs text-muted-foreground uppercase">
              <tr><th className="px-4 py-3">Report</th><th className="px-4 py-3">Client</th><th className="px-4 py-3">Period</th><th className="px-4 py-3">Created</th><th /></tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-4 py-3 font-medium"><span className="flex items-center gap-2"><FileText className="size-4 text-primary" /> {r.type} report</span></td>
                  <td className="px-4 py-3">{r.clientName}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{niceDate(r.periodStart)} – {niceDate(r.periodEnd)}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{new Date(r.createdAt).toLocaleString('en-IN')}</td>
                  <td className="px-4 py-3 text-right"><ButtonLink size="sm" variant="outline" href={`/report-view?id=${r.id}`}>Open</ButtonLink></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
