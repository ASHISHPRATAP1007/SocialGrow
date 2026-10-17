'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import { Facebook, Link2, MessageCircle, Plus, Youtube } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Field, P_LABEL, Panel, PlatformBadge, errMsg, selectClass } from '@/components/sg'
import { ClientPicker } from '@/components/client-picker'

const NAME = { facebook: 'Facebook', google: 'Google (YouTube)' }

/** Toast after coming back from the Facebook / Google login screen, then cleans the URL. */
export function OAuthResult() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const result = params.get('oauth')
  useEffect(() => {
    if (!result) return
    const provider = NAME[params.get('provider')] || 'Account'
    const added = Number(params.get('added') || 0)
    const found = Number(params.get('found') || 0)
    if (result === 'connected') {
      if (added) toast.success(`${provider} connect ho gaya — ${added} account(s) LIVE add hue`)
      else if (found) toast.success(`${provider} connect ho gaya — ${found} account mile. Neeche client chun kar add karein.`)
      else toast.success(`${provider} connect ho gaya`)
    } else if (result === 'cancelled') toast.error(`${provider} connect cancel ho gaya.`)
    else toast.error(params.get('message') || `${provider} connect nahi ho paya. Dobara try karein.`)
    refreshAll()
    router.replace(pathname)
  }, [result, params, router, pathname])
  return null
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

/** Creates (or reuses) the client's connect link and copies it. */
export async function shareConnectLink(client) {
  try {
    const { data } = await api.post(`/clients/${client.id}/connect-link`)
    const ok = await copyText(data.url)
    toast.success(ok ? 'Link copy ho gaya — client ko WhatsApp par bhejein' : data.url)
    return data.url
  } catch (err) {
    toast.error(errMsg(err))
    return null
  }
}

export function whatsappHref(client, url) {
  const text = `Namaste ${client.name}, apne social media accounts hamare reporting dashboard se jodne ke liye ye link kholiye aur Facebook / Google se login kijiye (aapka password hamare paas nahi aata): ${url}`
  return `https://wa.me/?text=${encodeURIComponent(text)}`
}

async function startLogin(provider, clientId, back) {
  const { data } = await api.get(`/integrations/${provider}/connect-url`, { params: { clientId: clientId || undefined, back } })
  window.location.href = data.url
}

export function LoginButtons({ clientId, back, status, disabled, size }) {
  const [busy, setBusy] = useState(null)
  const go = async (p) => {
    setBusy(p)
    try {
      await startLogin(p, clientId, back)
    } catch (err) {
      toast.error(errMsg(err))
      setBusy(null)
    }
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button size={size} disabled={disabled || busy !== null || !status?.meta?.oauthAvailable} onClick={() => go('facebook')}>
        <Facebook className="size-4" /> {busy === 'facebook' ? 'Opening…' : 'Connect with Facebook'}
      </Button>
      <Button size={size} variant="outline" disabled={disabled || busy !== null || !status?.google?.appConfigured} onClick={() => go('google')}>
        <Youtube className="size-4 text-red-600" /> {busy === 'google' ? 'Opening…' : 'Connect with Google'}
      </Button>
    </div>
  )
}

/** Social Accounts page: pick a client, then log in (agency has access) or send the client a link. */
export function ConnectPanel({ clients, status }) {
  const { data: available } = useApi('/accounts/available')
  const [clientId, setClientId] = useState('')
  const [link, setLink] = useState(null)
  const [adding, setAdding] = useState(null)
  const client = clients.find((c) => c.id === clientId)
  const notReady = !status.meta.oauthAvailable && !status.google.appConfigured

  async function add(item) {
    if (!clientId) return toast.error('Pehle client chunein')
    setAdding(item.platform + item.id)
    try {
      const { data } = await api.post('/accounts/add-connected', { clientId, items: [{ platform: item.platform, id: item.id }] })
      if (data.added.length) toast.success(`@${data.added[0].username} LIVE add hua`)
      else toast.error(data.errors[0]?.error || 'Add nahi ho paya')
      refreshAll()
    } catch (err) {
      toast.error(errMsg(err))
    } finally {
      setAdding(null)
    }
  }

  return (
    <Panel title="Accounts jodein — sirf login se, koi ID / key nahi" className="mb-4">
      {notReady && (
        <p className="mb-3 rounded-md bg-warning-soft p-3 text-xs">
          Login se connect abhi set nahi hai — platform owner ko Settings mein ek baar Facebook / Google app jodna hoga.
        </p>
      )}
      {clients.length === 0 ? (
        <p className="text-sm text-muted-foreground">Pehle Clients page se ek client add karein.</p>
      ) : (
        <>
          <div className="max-w-sm">
            <Field label="1. Kis client ke accounts?">
              <ClientPicker clients={clients} value={clientId} onChange={(id) => { setClientId(id); setLink(null) }} />
            </Field>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border p-4">
              <div className="text-sm font-semibold">2a. Page / channel ka access aapke paas hai</div>
              <p className="mb-3 mt-1 text-xs text-muted-foreground">Login karein — Pages, unse juda Instagram aur YouTube channel apne aap is client mein add ho jayenge.</p>
              <LoginButtons clientId={clientId} back="social-accounts" status={status} disabled={!clientId} size="sm" />
            </div>
            <div className="rounded-lg border p-4">
              <div className="text-sm font-semibold">2b. Access client ke paas hai</div>
              <p className="mb-3 mt-1 text-xs text-muted-foreground">Client ko link bhejein. Wo apne Facebook / Google se login karega — accounts yahan apne aap aa jayenge. Client ka password aapke paas nahi aata.</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={!client || notReady} onClick={async () => setLink(await shareConnectLink(client))}>
                  <Link2 className="size-4" /> Link copy karein
                </Button>
                {link && client && (
                  <a className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#25D366] px-3 text-sm font-medium text-white" href={whatsappHref(client, link)} target="_blank" rel="noreferrer">
                    <MessageCircle className="size-4" /> WhatsApp par bhejein
                  </a>
                )}
              </div>
              {link && <div className="mt-2 break-all rounded bg-muted px-2 py-1 text-[11px]">{link}</div>}
            </div>
          </div>
        </>
      )}

      {available?.length > 0 && (
        <div className="mt-4 rounded-lg border border-dashed p-4">
          <div className="text-sm font-semibold">Connected, par abhi kisi client mein nahi ({available.length})</div>
          <p className="mb-2 text-xs text-muted-foreground">Upar client chunein aur &quot;Add&quot; dabayein.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {available.map((i) => (
              <div key={i.platform + i.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <PlatformBadge platform={i.platform} label={false} />
                  <span className="truncate">{i.username ? `@${i.username}` : i.name}</span>
                  <span className="text-[11px] text-muted-foreground">{P_LABEL[i.platform]}</span>
                </div>
                <Button size="sm" variant="ghost" disabled={!clientId || adding !== null} onClick={() => add(i)}>
                  <Plus className="size-4" /> {adding === i.platform + i.id ? 'Adding…' : 'Add'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  )
}
