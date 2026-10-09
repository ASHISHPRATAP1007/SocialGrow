'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle2, CircleDashed, ExternalLink, KeyRound } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Panel, PlatformBadge, errMsg } from '@/components/sg'

function StatusPill({ ok, text }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${ok ? 'bg-success-soft text-success' : 'bg-muted text-muted-foreground'}`}>
      {ok ? <CheckCircle2 className="size-3.5" /> : <CircleDashed className="size-3.5" />} {text}
    </span>
  )
}

export function IntegrationsPanel({ canEdit }) {
  const { data: status } = useApi('/integrations/status')
  const [ytKey, setYtKey] = useState('')
  const [meta, setMeta] = useState({ token: '', appId: '', appSecret: '' })
  const [busy, setBusy] = useState(null)
  const [advanced, setAdvanced] = useState(false)

  if (!status) return null
  const owner = status.shared.isPlatformOwner
  const showYtForm = owner || !status.shared.youtube || status.youtube.configured || advanced
  const exp = status.meta.expiresAt ? new Date(status.meta.expiresAt) : null
  const daysLeft = exp ? Math.ceil((exp.getTime() - Date.now()) / 86400000) : null

  return (
    <Panel title={<span className="flex items-center gap-2"><KeyRound className="size-4 text-primary" /> Integrations (real data)</span>}>
      {owner ? (
        <p className="mb-4 rounded-md bg-secondary p-3 text-sm text-secondary-foreground">
          👑 Aap platform owner hain — yahan ki <b>YouTube key</b> aur <b>Instagram (Meta) connection</b> saari agencies ke liye apne aap use hoti hai. Facebook Pages hamesha har agency ke apne token se hi judte hain.
        </p>
      ) : (
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          {[
            ['youtube', status.youtube.ready, 'Ready — koi setup nahi'],
            ['instagram', status.meta.instagramReady, 'Ready — koi setup nahi'],
            ['facebook', status.meta.facebookReady, status.meta.facebookReady ? 'Aapke Pages connected' : 'Apne Pages ke liye neeche connect karein'],
          ].map(([p, ok, text]) => (
            <div key={p} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
              <PlatformBadge platform={p} />
              <StatusPill ok={!!ok} text={ok ? text : p === 'facebook' ? text : 'Abhi available nahi'} />
            </div>
          ))}
        </div>
      )}
      <p className="mb-4 text-sm text-muted-foreground">Keys safely server par save hoti hain — browser ya doosre users ko kabhi nahi dikhti.</p>

      {showYtForm ? (
        <div className="rounded-lg border p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <PlatformBadge platform="youtube" />
            <StatusPill ok={status.youtube.configured} text={status.youtube.configured ? `Connected ${status.youtube.keyHint}` : 'Not connected'} />
          </div>
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy('yt')
              try {
                await api.put('/integrations/youtube', { apiKey: ytKey })
                toast.success(ytKey ? 'YouTube API key save ho gayi' : 'YouTube key hata di')
                setYtKey('')
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              } finally {
                setBusy(null)
              }
            }}
          >
            <div className="flex-1">
              <Field label="YouTube Data API v3 key">
                <Input type="password" autoComplete="off" disabled={!canEdit} value={ytKey} onChange={(e) => setYtKey(e.target.value)} placeholder={status.youtube.configured ? 'Nayi key daalein (ya khaali chhod kar Save = remove)' : 'AIza...'} />
              </Field>
            </div>
            <Button type="submit" disabled={!canEdit || busy !== null}>{busy === 'yt' ? 'Saving…' : 'Save'}</Button>
          </form>
          <a className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline" href="https://console.cloud.google.com/apis/library/youtube.googleapis.com" target="_blank" rel="noreferrer">
            Google Cloud mein free key banayein <ExternalLink className="size-3" />
          </a>
        </div>
      ) : (
        <button type="button" className="text-xs text-muted-foreground underline" onClick={() => setAdvanced(true)}>
          Advanced: apni khud ki YouTube API key use karein (optional)
        </button>
      )}

      <div className="mt-4 rounded-lg border p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1.5"><PlatformBadge platform="instagram" /><PlatformBadge platform="facebook" /></div>
          <StatusPill ok={status.meta.configured} text={status.meta.configured ? `Connected ${status.meta.tokenHint}` : owner ? 'Not connected' : 'Optional — Facebook Pages ke liye'} />
        </div>
        {status.meta.configured && (
          <div className="mb-3 grid gap-1 rounded-md bg-muted/50 p-3 text-xs">
            <div>Instagram Business: <b>{status.meta.igUsername ? `@${status.meta.igUsername}` : 'Nahi mila (Instagram ko Facebook Page se link karein)'}</b></div>
            <div>Facebook Pages: <b>{status.meta.pages.length ? status.meta.pages.join(', ') : 'Koi nahi'}</b></div>
            <div>
              Token:{' '}
              <b className={daysLeft !== null && daysLeft < 10 ? 'text-destructive' : ''}>
                {daysLeft === null ? 'Short-lived (~1-2 ghante) — App ID + Secret ke saath dobara save karein' : `${daysLeft} din baaki (${exp.toLocaleDateString('en-IN')})`}
              </b>
            </div>
          </div>
        )}
        <form
          className="grid gap-2 sm:grid-cols-3"
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy('meta')
            try {
              const { data: r } = await api.post('/integrations/meta', { token: meta.token, appId: meta.appId || null, appSecret: meta.appSecret || null })
              toast.success(`Meta connected${r.igUsername ? ` · Instagram @${r.igUsername}` : ''} · ${r.pages.length} page(s)${r.longLived ? ' · 60-day token' : ''}`)
              setMeta({ token: '', appId: '', appSecret: '' })
              refreshAll()
            } catch (err) {
              toast.error(errMsg(err))
            } finally {
              setBusy(null)
            }
          }}
        >
          <Field label="App ID" hint="developers.facebook.com → App → Settings → Basic">
            <Input disabled={!canEdit} value={meta.appId} onChange={(e) => setMeta({ ...meta, appId: e.target.value })} />
          </Field>
          <Field label="App Secret" hint="Long-lived (60 din) token ke liye">
            <Input type="password" autoComplete="off" disabled={!canEdit} value={meta.appSecret} onChange={(e) => setMeta({ ...meta, appSecret: e.target.value })} />
          </Field>
          <Field label="User Access Token *" hint="Graph API Explorer se generate karein">
            <Input type="password" autoComplete="off" required disabled={!canEdit} value={meta.token} onChange={(e) => setMeta({ ...meta, token: e.target.value })} placeholder="EAA..." />
          </Field>
          <div className="flex flex-wrap gap-2 sm:col-span-3">
            <Button type="submit" disabled={!canEdit || busy !== null}>{busy === 'meta' ? 'Connecting…' : 'Save & connect'}</Button>
            {status.meta.configured && canEdit && (
              <Button variant="ghost" onClick={() => confirm('Meta connection hatayein?') && api.delete('/integrations/meta').then(refreshAll)}>Disconnect</Button>
            )}
          </div>
        </form>
        <p className="mt-2 text-xs text-muted-foreground">
          Token permissions: <code>instagram_basic, pages_show_list, pages_read_engagement, instagram_manage_insights, business_management</code>
        </p>
        <a className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline" href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noreferrer">
          Graph API Explorer kholein <ExternalLink className="size-3" />
        </a>
      </div>
    </Panel>
  )
}
