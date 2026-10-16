'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Link2, Unplug, Info, RefreshCw } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ConnectPanel, OAuthResult } from '@/components/connect'
import { DemoBadge, LiveBadge, EmptyState, Field, Loading, PLATFORMS, P_LABEL, PageHeader, Panel, PlatformBadge, can, errMsg, fmt, selectClass, useMe } from '@/components/sg'

const PLACEHOLDER = {
  youtube: '@channelhandle, channel URL ya video link',
  instagram: 'business/creator username',
  facebook: 'Page username, ID ya naam',
}

function ago(ts) {
  if (!ts) return 'never'
  const m = Math.round((Date.now() - ts) / 60000)
  if (m < 1) return 'abhi'
  if (m < 60) return `${m} min pehle`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} ghante pehle`
  return `${Math.round(h / 24)} din pehle`
}

export default function AccountsPage() {
  return (
    <>
      <Suspense fallback={null}>
        <OAuthResult />
      </Suspense>
      <AccountsView />
    </>
  )
}

function AccountsView() {
  const me = useMe()
  const { data: accounts } = useApi('/accounts')
  const { data: clients } = useApi('/clients')
  const { data: projects } = useApi('/projects')
  const { data: integ } = useApi('/integrations/status')
  const [platform, setPlatform] = useState(null)
  const [projectId, setProjectId] = useState('')
  const [handle, setHandle] = useState('')
  const [busy, setBusy] = useState(false)
  const [syncing, setSyncing] = useState(null)
  const manage = can(me.role, 'manage')

  if (!accounts || !projects || !integ || !clients) return <Loading />

  const liveReady = (p) => (p === 'youtube' ? integ.youtube.ready : p === 'instagram' ? integ.meta.instagramReady : integ.meta.facebookReady)

  async function submit(mode) {
    if (!platform) return
    if (!projectId) return toast.error('Project chunein')
    if (!handle.trim()) return toast.error('Username / handle daalein')
    setBusy(true)
    try {
      if (mode === 'live') {
        const { data: r } = await api.post('/accounts/live', { projectId, platform, handle })
        toast.success(`@${r.username} LIVE connect hua — ${fmt(r.followers)} followers, ${r.posts} posts`)
      } else {
        await api.post('/accounts/demo', { projectId, platform, username: handle })
        toast.success('Demo mode mein connect hua')
      }
      setHandle('')
      setPlatform(null)
      refreshAll()
    } catch (err) {
      toast.error(errMsg(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="Social Accounts" subtitle="Official APIs se real data — har 6 ghante mein auto-sync." />

      {manage && <ConnectPanel clients={clients} status={integ} />}

      {manage && (
        <Panel title="Username se jodein (public / competitor accounts)" className="mb-4">
          <p className="-mt-1 mb-3 text-xs text-muted-foreground">Jinka login aapke paas nahi — jaise competitor. YouTube aur Instagram Business ka public data milega.</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {PLATFORMS.map((p) => (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                className={`flex items-center justify-between rounded-lg border p-4 text-left transition hover:border-primary ${platform === p ? 'border-primary ring-2 ring-primary/20' : ''}`}
              >
                <PlatformBadge platform={p} />
                {liveReady(p) ? <LiveBadge /> : <Link2 className="size-4 text-muted-foreground" />}
              </button>
            ))}
          </div>

          {platform && (
            <div className="mt-4 rounded-lg border bg-muted/40 p-4">
              {!liveReady(platform) && (
                <div className="mb-3 flex gap-2 rounded-md bg-warning-soft p-3 text-xs">
                  <Info className="mt-0.5 size-4 shrink-0 text-warning" />
                  <div>
                    {platform === 'facebook' ? (
                      <>
                        Facebook Page jodne ke liye <Link href="/settings" className="font-semibold text-primary underline">Settings → Integrations</Link> mein apna Meta
                        account connect karein — isse aap sirf <b>apne</b> (ya client ke diye access wale) Pages jod sakte hain.
                      </>
                    ) : (
                      <>{P_LABEL[platform]} live data abhi available nahi hai. Tab tak Demo mode use kar sakte hain.</>
                    )}
                  </div>
                </div>
              )}
              {projects.length === 0 ? (
                <p className="text-sm text-muted-foreground">Pehle ek project banayein.</p>
              ) : (
                <form
                  className="grid gap-3 sm:grid-cols-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    void submit(liveReady(platform) ? 'live' : 'demo')
                  }}
                >
                  <Field label="Project">
                    <select className={selectClass} value={projectId} onChange={(e) => setProjectId(e.target.value)} required>
                      <option value="">Select project</option>
                      {projects.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.clientName})</option>)}
                    </select>
                  </Field>
                  <Field label={platform === 'youtube' ? 'Channel' : platform === 'facebook' ? 'Facebook Page' : 'Instagram username'}>
                    <Input required value={handle} onChange={(e) => setHandle(e.target.value)} placeholder={PLACEHOLDER[platform]} />
                  </Field>
                  <div className="flex flex-wrap items-end gap-2">
                    {liveReady(platform) ? (
                      <>
                        <Button type="submit" disabled={busy}>{busy ? 'Fetching real data…' : 'Connect (Live)'}</Button>
                        <Button variant="ghost" disabled={busy} onClick={() => void submit('demo')}>Demo</Button>
                      </>
                    ) : (
                      <Button type="submit" disabled={busy}>{busy ? 'Connecting…' : 'Connect (Demo mode)'}</Button>
                    )}
                  </div>
                </form>
              )}
            </div>
          )}
        </Panel>
      )}

      {accounts.length === 0 ? (
        <EmptyState title="Koi account connect nahi" text="Upar se platform chunein aur account connect karein." />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-xs text-muted-foreground uppercase">
              <tr>
                <th className="px-4 py-3">Account <span className="normal-case font-normal">(click = poori details)</span></th>
                <th className="px-4 py-3">Client / Project</th>
                <th className="px-4 py-3">Followers</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id} className="border-t align-top">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <PlatformBadge platform={a.platform} label={false} />
                      <div>
                        <Link href={`/account?id=${a.id}`} className="font-medium text-primary hover:underline">@{a.username}</Link>
                        {a.displayName && a.displayName !== a.username && <div className="text-xs text-muted-foreground">{a.displayName}</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <div className="font-medium">{a.clientName}</div>
                    <div className="text-muted-foreground">{a.projectName}</div>
                  </td>
                  <td className="px-4 py-3 font-semibold">{a.followers != null ? fmt(a.followers) : '—'}</td>
                  <td className="px-4 py-3">
                    {a.mode === 'api' ? (
                      <div className="space-y-1">
                        <LiveBadge />
                        <div className="text-[11px] text-muted-foreground">Synced {ago(a.lastSyncedAt)}</div>
                      </div>
                    ) : (
                      <DemoBadge />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs font-semibold ${a.status === 'connected' && !a.syncError ? 'text-success' : 'text-warning'}`}>● {a.status.replace('_', ' ')}</span>
                    {a.syncError && <div className="mt-1 max-w-56 text-[11px] text-destructive">{a.syncError}</div>}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {manage && a.mode === 'api' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={syncing === a.id}
                        onClick={async () => {
                          setSyncing(a.id)
                          try {
                            const { data: r } = await api.post(`/accounts/${a.id}/sync`)
                            if (r.error) toast.error(r.error)
                            else toast.success('Sync complete')
                            refreshAll()
                          } catch (e) {
                            toast.error(errMsg(e))
                          } finally {
                            setSyncing(null)
                          }
                        }}
                      >
                        <RefreshCw className={`size-4 ${syncing === a.id ? 'animate-spin' : ''}`} /> Sync
                      </Button>
                    )}
                    {manage && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          if (!confirm(`@${a.username} disconnect karein? Iska stored data bhi delete hoga.`)) return
                          try {
                            await api.delete(`/accounts/${a.id}`)
                            toast.success('Disconnected')
                            refreshAll()
                          } catch (err) {
                            toast.error(errMsg(err))
                          }
                        }}
                      >
                        <Unplug className="size-4" /> Disconnect
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Note: Live accounts ka graph connect karne ke din se banna shuru hota hai (platforms purani daily history free API mein nahi dete). Posts aur unke likes/comments turant dikhte hain.
      </p>
    </>
  )
}
