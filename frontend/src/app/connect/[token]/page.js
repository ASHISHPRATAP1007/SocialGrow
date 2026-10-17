'use client'

import { Suspense, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { CheckCircle2, Facebook, Lock, ShieldCheck, Youtube } from 'lucide-react'
import { api, fetcher } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Loading, PlatformBadge, errMsg } from '@/components/sg'

const PROVIDER = { facebook: 'Facebook', google: 'Google (YouTube)' }

/** Public page a client opens from the agency's link — no SocialGrow account needed. */
export default function ConnectPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ConnectView />
    </Suspense>
  )
}

function Result() {
  const params = useSearchParams()
  const result = params.get('oauth')
  if (!result) return null
  const provider = PROVIDER[params.get('provider')] || 'Account'
  const added = Number(params.get('added') || 0)
  const ok = result === 'connected'
  return (
    <div className={`mb-5 rounded-lg p-4 text-sm ${ok ? 'bg-success-soft text-success' : 'bg-destructive/10 text-destructive'}`}>
      {ok
        ? added
          ? `✅ ${provider} jud gaya — ${added} account(s) add hue. Shukriya! Aap ye page band kar sakte hain.`
          : `✅ ${provider} jud gaya. Koi naya account nahi mila (shayad pehle se jude hain).`
        : result === 'cancelled'
          ? `${provider} login cancel hua. Dobara try kar sakte hain.`
          : params.get('message') || `${provider} connect nahi ho paya. Dobara try karein.`}
    </div>
  )
}

function ConnectView() {
  const { token } = useParams()
  const { data, error, isLoading } = useSWR(`/public/connect/${token}`, fetcher)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  async function start(provider) {
    setBusy(provider)
    setErr(null)
    try {
      const { data: r } = await api.get(`/public/connect/${token}/start`, { params: { provider } })
      window.location.href = r.url
    } catch (e) {
      setErr(errMsg(e))
      setBusy(null)
    }
  }

  if (isLoading) return <Loading />

  return (
    <div className="min-h-screen bg-muted/40 px-4 py-10">
      <div className="mx-auto max-w-lg rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
        {error || !data ? (
          <div className="text-center">
            <Lock className="mx-auto mb-3 size-8 text-muted-foreground" />
            <h1 className="text-lg font-bold">Link kaam nahi kar raha</h1>
            <p className="mt-2 text-sm text-muted-foreground">{errMsg(error) || 'Ye link expire ho gaya ya galat hai.'} Apni agency se naya link maangein.</p>
          </div>
        ) : (
          <>
            <div className="mb-1 text-xs font-semibold tracking-wide uppercase" style={data.brandColor ? { color: data.brandColor } : undefined}>
              {data.agencyName}
            </div>
            <h1 className="text-xl font-extrabold">Namaste {data.clientName} 👋</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              <b>{data.agencyName}</b> aapke social media ki growth report banana chahti hai. Neeche apne Facebook ya Google account se login
              karein — bas itna hi.
            </p>

            <div className="mt-5">
              <Result />
            </div>

            <div className="grid gap-3">
              <Button className="h-12 text-base" disabled={!data.providers.facebook || busy !== null} onClick={() => start('facebook')}>
                <Facebook className="size-5" /> {busy === 'facebook' ? 'Facebook khul raha hai…' : 'Facebook se jodein (Page + Instagram)'}
              </Button>
              <Button variant="outline" className="h-12 text-base" disabled={!data.providers.google || busy !== null} onClick={() => start('google')}>
                <Youtube className="size-5 text-red-600" /> {busy === 'google' ? 'Google khul raha hai…' : 'Google se jodein (YouTube)'}
              </Button>
            </div>
            {err && <p className="mt-3 text-sm text-destructive">{err}</p>}

            {data.connected.length > 0 && (
              <div className="mt-6">
                <div className="mb-2 text-sm font-semibold">Jude hue accounts</div>
                <div className="space-y-2">
                  {data.connected.map((a) => (
                    <div key={a.platform + a.username} className="flex items-center gap-2 rounded-md border p-2 text-sm">
                      <PlatformBadge platform={a.platform} label={false} /> @{a.username}
                      <CheckCircle2 className="ml-auto size-4 text-success" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-6 flex gap-2 rounded-md bg-muted p-3 text-xs text-muted-foreground">
              <ShieldCheck className="size-4 shrink-0 text-success" />
              <span>
                Aapka password kisi ko nahi milta — login seedha Facebook / Google par hota hai. Agency aapka data <b>padh</b> sakti hai aur YouTube par
                comments ka <b>reply</b> / video <b>upload</b> kar sakti hai (sirf jab team khud kare). Kuch delete ya apne aap post nahi hota. Kabhi bhi Facebook /
                Google settings se access hata sakte hain.
              </span>
            </div>
          </>
        )}
        <div className="mt-6 text-center text-[11px] text-muted-foreground">Powered by SocialGrow AI</div>
      </div>
    </div>
  )
}
