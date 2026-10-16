'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { api, refreshAll } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, PageHeader, Panel, can, errMsg, useMe } from '@/components/sg'
import { IntegrationsPanel } from '@/components/integrations-panel'
import { OAuthResult } from '@/components/connect'

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <OAuthResult />
      <SettingsForm />
    </Suspense>
  )
}

function SettingsForm() {
  const me = useMe()
  const a = me.agency
  const [f, setF] = useState({
    name: a.name,
    brandName: a.brandName ?? '',
    brandColor: a.brandColor ?? '',
    reportFooter: a.reportFooter ?? '',
    hide: !!a.hideSocialGrowBranding,
  })
  const admin = can(me.role, 'admin')
  const wl = me.limits.whiteLabel

  return (
    <>
      <PageHeader title="Settings" subtitle="Integrations, workspace aur white-label branding" />
      <div className="mb-4 max-w-3xl">
        <IntegrationsPanel canEdit={admin} />
      </div>
      <form
        className="grid max-w-3xl gap-4"
        onSubmit={async (e) => {
          e.preventDefault()
          try {
            await api.put('/settings', {
              name: f.name,
              brandName: wl ? f.brandName : null,
              brandColor: wl ? f.brandColor || null : null,
              reportFooter: wl ? f.reportFooter : null,
              hideSocialGrowBranding: wl ? f.hide : null,
            })
            toast.success('Settings save ho gayi')
            refreshAll()
          } catch (err) {
            toast.error(errMsg(err))
          }
        }}
      >
        <Panel title="Workspace">
          <Field label="Agency / business name">
            <Input value={f.name} disabled={!admin} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
        </Panel>
        <Panel title="White label" action={!wl && <Link href="/billing" className="text-sm text-primary hover:underline">Agency plan required →</Link>}>
          <fieldset disabled={!wl || !admin} className="grid gap-3 disabled:opacity-60 sm:grid-cols-2">
            <Field label="Brand name (reports + sidebar)"><Input value={f.brandName} onChange={(e) => setF({ ...f, brandName: e.target.value })} placeholder="ABC Digital" /></Field>
            <Field label="Primary color" hint="#RRGGBB format">
              <div className="flex gap-2">
                <input type="color" aria-label="Pick color" className="h-9 w-12 rounded border" value={f.brandColor || '#6d4aed'} onChange={(e) => setF({ ...f, brandColor: e.target.value })} />
                <Input value={f.brandColor} onChange={(e) => setF({ ...f, brandColor: e.target.value })} placeholder="#6d4aed" />
              </div>
            </Field>
            <Field label="Report footer"><Input value={f.reportFooter} onChange={(e) => setF({ ...f, reportFooter: e.target.value })} placeholder="ABC Digital Pvt Ltd · www.abcdigital.in" /></Field>
            <label className="flex items-center gap-2 pt-6 text-sm">
              <input type="checkbox" checked={f.hide} onChange={(e) => setF({ ...f, hide: e.target.checked })} />
              Reports se &quot;Powered by SocialGrow AI&quot; hatayein
            </label>
          </fieldset>
          {wl && (
            <div className="mt-4 rounded-lg border p-4">
              <div className="text-xs text-muted-foreground">Report preview</div>
              <div className="mt-2 border-b-4 pb-2" style={f.brandColor ? { borderColor: f.brandColor } : undefined}>
                <div className="font-extrabold uppercase" style={f.brandColor ? { color: f.brandColor } : undefined}>{f.brandName || f.name}</div>
                <div className="text-sm font-bold">Social Media Performance Report</div>
              </div>
              <div className="mt-2 text-center text-[11px] text-muted-foreground">{f.reportFooter || f.brandName || f.name}</div>
            </div>
          )}
        </Panel>
        {admin && <div><Button type="submit">Save settings</Button></div>}
      </form>
    </>
  )
}
