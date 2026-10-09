'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { BarChart3, Bot, FileText, Users, Sparkles, ShieldCheck } from 'lucide-react'
import { api, getToken, setToken } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Loading, errMsg } from '@/components/sg'

const FEATURES = [
  { icon: BarChart3, title: 'Real analytics', text: 'Instagram, Facebook aur YouTube ke followers, views aur engagement ek jagah.' },
  { icon: Bot, title: 'AI Growth Analyst', text: 'Poochiye "engagement kyun gira?" — AI aapke data se jawab dega.' },
  { icon: Sparkles, title: 'AI Content', text: 'Hooks, captions, hashtags aur 30-day content calendar.' },
  { icon: Users, title: 'Agency ready', text: 'Clients, projects, team roles aur campaigns.' },
  { icon: FileText, title: 'White-label reports', text: 'Aapke brand ke saath AI-written client reports, PDF mein.' },
  { icon: ShieldCheck, title: 'Authentic growth only', text: 'Koi fake followers ya bots nahi — sirf real data aur strategy.' },
]

export default function Home() {
  const router = useRouter()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    if (getToken()) router.replace('/dashboard')
    else setChecking(false)
  }, [router])

  if (checking) return <Loading label="Session check ho raha hai…" />

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 lg:grid-cols-[1.2fr_1fr] lg:py-16">
        <div className="flex flex-col justify-center">
          <div className="mb-6 flex items-center gap-2">
            <div className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Sparkles className="size-5" />
            </div>
            <span className="text-lg font-extrabold tracking-tight">SocialGrow AI</span>
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-balance sm:text-5xl">
            Social media growth ko <span className="text-primary">data aur AI</span> se samjhiye.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted-foreground">
            Agencies aur brands ke liye ek platform: analytics, AI insights, content planning, campaigns aur client reports.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className="flex gap-3 rounded-xl border bg-card p-4">
                <f.icon className="mt-0.5 size-5 shrink-0 text-primary" />
                <div>
                  <div className="text-sm font-semibold">{f.title}</div>
                  <div className="text-xs text-muted-foreground">{f.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="flex items-center">
          <AuthCard onDone={() => router.replace('/dashboard')} />
        </div>
      </div>
    </div>
  )
}

function AuthCard({ onDone }) {
  // step: 'signIn' | 'signUp' | 'forgot' | { reset: email }
  const [step, setStep] = useState('signIn')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [agencyName, setAgencyName] = useState('')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (step === 'signIn') {
        const { data } = await api.post('/auth/login', { email, password })
        setToken(data.accessToken)
        onDone()
      } else if (step === 'signUp') {
        if (password.length < 8) throw new Error('Password kam se kam 8 characters ka ho.')
        const { data } = await api.post('/auth/register', { email, password, agencyName, phone })
        setToken(data.accessToken)
        onDone()
      } else if (step === 'forgot') {
        await api.post('/auth/forgot-password', { email })
        setStep({ reset: email })
      } else {
        const { data } = await api.post('/auth/reset-password', { email: step.reset, code, newPassword })
        setToken(data.accessToken)
        onDone()
      }
    } catch (err) {
      setError(err?.response ? errMsg(err) : err.message)
    } finally {
      setBusy(false)
    }
  }

  const title =
    step === 'signIn' ? 'Sign in' : step === 'signUp' ? '30 din free trial shuru karein' : step === 'forgot' ? 'Password reset' : 'Naya password set karein'

  return (
    <div className="w-full rounded-2xl border bg-card p-6 shadow-lg sm:p-8">
      <h2 className="text-xl font-bold">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {step === 'signUp'
          ? 'Turant 30 din ka FREE Pro trial — koi card nahi chahiye.'
          : typeof step === 'object'
            ? `Code ${step.reset} par bheja gaya hai.`
            : 'Apne workspace mein login karein.'}
      </p>
      <form className="mt-6 space-y-4" onSubmit={submit}>
        {typeof step === 'object' ? (
          <>
            <Field label="6-digit code">
              <Input inputMode="numeric" pattern="\d{6}" required placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <Field label="New password">
              <Input type="password" minLength={8} required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </Field>
          </>
        ) : (
          <>
            {step === 'signUp' && (
              <>
                <Field label="Agency / Business name *">
                  <Input placeholder="ABC Digital" required value={agencyName} onChange={(e) => setAgencyName(e.target.value)} />
                </Field>
                <Field label="Mobile (WhatsApp) *">
                  <Input type="tel" inputMode="tel" placeholder="98765 43210" required pattern="[0-9+ ]{10,15}" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </Field>
              </>
            )}
            <Field label="Email">
              <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            {step !== 'forgot' && (
              <Field label="Password">
                <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
            )}
          </>
        )}
        {error && <div className="rounded-md bg-danger-soft px-3 py-2 text-sm text-destructive">{error}</div>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? 'Please wait…' : step === 'signIn' ? 'Sign in' : step === 'signUp' ? 'Create account' : step === 'forgot' ? 'Send reset code' : 'Reset password'}
        </Button>
      </form>
      <div className="mt-4 flex flex-col gap-2 text-center text-sm">
        {step === 'signIn' && (
          <>
            <button type="button" className="text-primary hover:underline" onClick={() => setStep('signUp')}>
              Naya account — 30 din free trial
            </button>
            <button type="button" className="text-muted-foreground hover:underline" onClick={() => setStep('forgot')}>
              Password bhool gaye?
            </button>
          </>
        )}
        {step !== 'signIn' && (
          <button type="button" className="text-primary hover:underline" onClick={() => setStep('signIn')}>
            Back to sign in
          </button>
        )}
      </div>
    </div>
  )
}
