'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle2, CircleDashed, Copy, ExternalLink, KeyRound } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Panel, PlatformBadge, errMsg } from '@/components/sg'
import { LoginButtons } from '@/components/connect'

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
  const [gApp, setGApp] = useState({ clientId: '', clientSecret: '' })

  if (!status) return null
  const owner = status.shared.isPlatformOwner
  const m = status.meta
  const showYtForm = owner || !status.shared.youtube || status.youtube.configured || advanced
  const showTokenForm = owner || advanced || !m.oauthAvailable
  const exp = m.expiresAt ? new Date(m.expiresAt) : null
  const daysLeft = exp ? Math.ceil((exp.getTime() - Date.now()) / 86400000) : null

  return (
    <Panel title={<span className="flex items-center gap-2"><KeyRound className="size-4 text-primary" /> Integrations (real data)</span>}>
      {owner ? (
        <div className="mb-4 rounded-md bg-secondary p-3 text-sm text-secondary-foreground">
          👑 Aap platform owner hain. Yahan <b>ek baar</b> setup karein — phir har agency ko YouTube aur Instagram apne aap milega, aur Facebook wo
          <b> ek click</b> se jod lenge. Token kabhi expire nahi hota, kuch update nahi karna padta.
          <ol className="mt-2 list-decimal space-y-0.5 pl-5 text-xs">
            <li className={status.youtube.configured ? 'line-through opacity-70' : ''}>YouTube API key save karein</li>
            <li className={m.appConfigured ? 'line-through opacity-70' : ''}>Meta App ID + App Secret + apna token save karein</li>
            <li>Meta App → Facebook Login → Settings → <b>Valid OAuth Redirect URIs</b> mein neeche wala URL daalein</li>
            <li className={status.google.appConfigured ? 'line-through opacity-70' : ''}>Google OAuth Client ID + Secret save karein (YouTube login ke liye)</li>
          </ol>
        </div>
      ) : (
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          {[
            ['youtube', status.youtube.ready, 'Ready — koi setup nahi'],
            ['instagram', m.instagramReady, 'Ready — koi setup nahi'],
            ['facebook', m.facebookReady, m.facebookReady ? `${m.pages.length} Page(s) connected` : 'Login se connect karein'],
          ].map(([p, ok, text]) => (
            <div key={p} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
              <PlatformBadge platform={p} />
              <StatusPill ok={!!ok} text={ok || p === 'facebook' ? text : 'Abhi available nahi'} />
            </div>
          ))}
        </div>
      )}

      {showYtForm ? (
        <div className="rounded-lg border p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <PlatformBadge platform="youtube" />
            <StatusPill ok={status.youtube.configured} text={status.youtube.configured ? `Connected ${status.youtube.keyHint} · never expires` : 'Not connected'} />
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
      ) : null}

      <div className="mt-4 rounded-lg border p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1.5">{owner && <PlatformBadge platform="instagram" />}<PlatformBadge platform="facebook" /></div>
          <StatusPill
            ok={m.configured}
            text={m.configured ? (m.neverExpires ? 'Connected · never expires' : `Connected ${m.tokenHint}`) : owner ? 'Not connected' : 'Not connected'}
          />
        </div>

        {m.configured && (
          <div className="mb-3 grid gap-1 rounded-md bg-muted/50 p-3 text-xs">
            {owner && <div>Instagram Business: <b>{m.igUsername ? `@${m.igUsername}` : 'Nahi mila (Instagram ko Facebook Page se link karein)'}</b></div>}
            <div>Facebook Pages: <b>{m.pages.length ? m.pages.join(', ') : 'Koi nahi'}</b></div>
            {!m.neverExpires && (
              <div>
                Token:{' '}
                <b className={daysLeft !== null && daysLeft < 10 ? 'text-destructive' : ''}>
                  {daysLeft === null ? 'Short-lived — App ID + Secret ke saath dobara save karein' : `${daysLeft} din baaki`}
                </b>
              </div>
            )}
          </div>
        )}

        {!owner && (
          <div className="space-y-2">
            <LoginButtons back="settings" status={status} disabled={!canEdit} />
            <p className="text-xs text-muted-foreground">
              Facebook / Google se login karein — Pages, Instagram aur YouTube channels mil jayenge. Unko client mein add karne ke liye
              <b> Social Accounts</b> page kholein (wahan se client ko connect link bhi bhej sakte hain).
            </p>
            {status.google.channels.length > 0 && <div className="text-xs">YouTube channels: <b>{status.google.channels.join(', ')}</b></div>}
            {m.configured && canEdit && (
              <Button variant="ghost" size="sm" onClick={() => confirm('Facebook connection hatayein?') && api.delete('/integrations/meta').then(refreshAll)}>Disconnect Facebook</Button>
            )}
          </div>
        )}

        {owner && m.redirectUri && (
          <div className="mb-3 rounded-md border p-3 text-xs">
            <div className="mb-1 font-semibold">Meta App mein ye Redirect URI daalein (Facebook Login → Settings → Valid OAuth Redirect URIs):</div>
            <div className="flex items-center gap-2">
              <code className="break-all rounded bg-muted px-2 py-1">{m.redirectUri}</code>
              <button aria-label="Copy redirect URI" onClick={() => { void navigator.clipboard.writeText(m.redirectUri); toast.success('Copied') }}><Copy className="size-3.5" /></button>
            </div>
          </div>
        )}

        {showTokenForm && (owner || advanced) && (
          <form
            className="grid gap-2 sm:grid-cols-3"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy('meta')
              try {
                const { data: r } = await api.post('/integrations/meta', { token: meta.token, appId: meta.appId || null, appSecret: meta.appSecret || null })
                toast.success(`Meta connected${r.igUsername ? ` · Instagram @${r.igUsername}` : ''} · ${r.pages.length} page(s)${r.neverExpires ? ' · never expires' : ''}`)
                setMeta({ token: '', appId: '', appSecret: '' })
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              } finally {
                setBusy(null)
              }
            }}
          >
            {owner && (
              <>
                <Field label="App ID" hint="developers.facebook.com → App → Settings → Basic">
                  <Input disabled={!canEdit} value={meta.appId} onChange={(e) => setMeta({ ...meta, appId: e.target.value })} placeholder={m.appConfigured ? 'Saved ✓ (badalna ho toh daalein)' : ''} />
                </Field>
                <Field label="App Secret" hint="Ek baar — saari agencies ke Facebook connect ke liye">
                  <Input type="password" autoComplete="off" disabled={!canEdit} value={meta.appSecret} onChange={(e) => setMeta({ ...meta, appSecret: e.target.value })} placeholder={m.appConfigured ? 'Saved ✓' : ''} />
                </Field>
              </>
            )}
            <Field label="User Access Token *" hint="Graph API Explorer se generate karein">
              <Input type="password" autoComplete="off" required disabled={!canEdit} value={meta.token} onChange={(e) => setMeta({ ...meta, token: e.target.value })} placeholder="EAA..." />
            </Field>
            <div className="flex flex-wrap gap-2 sm:col-span-3">
              <Button type="submit" disabled={!canEdit || busy !== null}>{busy === 'meta' ? 'Connecting…' : 'Save & connect'}</Button>
              {m.configured && canEdit && owner && (
                <Button variant="ghost" onClick={() => confirm('Meta connection hatayein? Saari agencies ka Instagram band ho jayega.') && api.delete('/integrations/meta').then(refreshAll)}>Disconnect</Button>
              )}
            </div>
            {owner && (
              <p className="text-xs text-muted-foreground sm:col-span-3">
                Token permissions: <code>instagram_basic, pages_show_list, pages_read_engagement, instagram_manage_insights, business_management</code> ·{' '}
                <a className="text-primary hover:underline" href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noreferrer">Graph API Explorer</a>
              </p>
            )}
          </form>
        )}
      </div>

      {owner && (
        <div className="mt-4 rounded-lg border p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">Google login (YouTube) — Connect with Google</span>
            <StatusPill ok={status.google.appConfigured} text={status.google.appConfigured ? `Set ${status.google.clientIdHint || ''}` : 'Not set'} />
          </div>
          {status.google.redirectUri && (
            <div className="mb-3 rounded-md border p-3 text-xs">
              <div className="mb-1 font-semibold">Google Cloud → APIs &amp; Services → Credentials → OAuth client (Web) → Authorized redirect URIs mein ye daalein:</div>
              <div className="flex items-center gap-2">
                <code className="break-all rounded bg-muted px-2 py-1">{status.google.redirectUri}</code>
                <button aria-label="Copy Google redirect URI" onClick={() => { void navigator.clipboard.writeText(status.google.redirectUri); toast.success('Copied') }}><Copy className="size-3.5" /></button>
              </div>
            </div>
          )}
          <form
            className="grid gap-2 sm:grid-cols-3"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy('google')
              try {
                await api.put('/integrations/google-app', gApp)
                toast.success('Google login set ho gaya — ab sab "Connect with Google" kar sakte hain')
                setGApp({ clientId: '', clientSecret: '' })
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              } finally {
                setBusy(null)
              }
            }}
          >
            <Field label="OAuth Client ID">
              <Input required disabled={!canEdit} value={gApp.clientId} onChange={(e) => setGApp({ ...gApp, clientId: e.target.value })} placeholder={status.google.appConfigured ? 'Saved ✓ (badalna ho toh daalein)' : '…apps.googleusercontent.com'} />
            </Field>
            <Field label="OAuth Client Secret">
              <Input required type="password" autoComplete="off" disabled={!canEdit} value={gApp.clientSecret} onChange={(e) => setGApp({ ...gApp, clientSecret: e.target.value })} placeholder={status.google.appConfigured ? 'Saved ✓' : 'GOCSPX-…'} />
            </Field>
            <div className="flex items-end"><Button type="submit" disabled={!canEdit || busy !== null}>{busy === 'google' ? 'Saving…' : 'Save'}</Button></div>
          </form>
          <p className="mt-2 text-xs text-muted-foreground">
            Scope: <code>youtube.readonly</code> · OAuth consent screen ko <b>In production</b> rakhein (Testing mode mein login 7 din baad expire hota hai).
          </p>
        </div>
      )}

      {!owner && !advanced && (
        <button type="button" className="mt-3 text-xs text-muted-foreground underline" onClick={() => setAdvanced(true)}>
          Advanced: apni khud ki API key / token use karein (optional)
        </button>
      )}
    </Panel>
  )
}
