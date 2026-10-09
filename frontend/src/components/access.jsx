'use client'

import Link from 'next/link'
import { Clock, XCircle, Ban, Sparkles, AlertTriangle, Lock } from 'lucide-react'
import { signOut } from '@/lib/api'
import { Button } from '@/components/ui/button'

/** Full-screen state for accounts that can't use the app (pending / rejected / suspended). */
export function AccessGate({ me }) {
  const s = me.access.state
  const Icon = s === 'pending' ? Clock : s === 'rejected' ? XCircle : Ban
  const title = s === 'pending' ? 'Aapka account review mein hai' : s === 'rejected' ? 'Account approve nahi hua' : 'Account suspend hai'
  const text =
    s === 'pending'
      ? 'Registration ke liye shukriya! Hamari team aapki details check kar rahi hai. Approve hote hi aapka free Pro trial shuru ho jayega.'
      : 'Agar aapko lagta hai ye galti hai, toh support se contact karein.'
  return (
    <div className="grid min-h-screen place-items-center bg-background px-4">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 text-center shadow-lg">
        <div className="mx-auto mb-4 flex items-center justify-center gap-2">
          <div className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Sparkles className="size-5" />
          </div>
          <span className="text-lg font-extrabold">SocialGrow AI</span>
        </div>
        <Icon className={`mx-auto size-12 ${s === 'pending' ? 'text-warning' : 'text-destructive'}`} />
        <h1 className="mt-4 text-xl font-bold">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{text}</p>
        <div className="mt-6 rounded-lg bg-muted/60 p-3 text-left text-xs">
          <div><span className="text-muted-foreground">Agency:</span> <b>{me.agency.name}</b></div>
          <div><span className="text-muted-foreground">Email:</span> <b>{me.email}</b></div>
        </div>
        <Button variant="outline" className="mt-6 w-full" onClick={signOut}>
          Sign out
        </Button>
      </div>
    </div>
  )
}

/** Thin banner at the top of the app for trial / grace / expired states. */
export function AccessBanner({ me }) {
  const a = me.access
  if (a.state === 'trial') {
    const urgent = (a.daysLeft ?? 99) <= 5
    return (
      <div className={`no-print flex flex-wrap items-center justify-center gap-2 px-4 py-2 text-center text-sm ${urgent ? 'bg-warning-soft text-foreground' : 'bg-secondary text-secondary-foreground'}`}>
        <Sparkles className="size-4" />
        <span>
          Free Pro trial: <b>{a.daysLeft} din baaki</b>
          {urgent ? ' — kaam chalu rakhne ke liye plan le lijiye.' : ''}
        </span>
        <Link href="/billing" className="font-semibold underline">Plan dekhein</Link>
      </div>
    )
  }
  if (a.state === 'grace') {
    return (
      <div className="no-print flex flex-wrap items-center justify-center gap-2 bg-warning-soft px-4 py-2 text-center text-sm">
        <AlertTriangle className="size-4 text-warning" />
        <span>Subscription expire ho gaya — <b>{a.daysLeft} din</b> ka grace period. Uske baad account read-only ho jayega.</span>
        <Link href="/billing" className="font-semibold underline">Abhi renew karein</Link>
      </div>
    )
  }
  if (a.state === 'expired') {
    return (
      <div className="no-print flex flex-wrap items-center justify-center gap-2 bg-destructive px-4 py-2 text-center text-sm text-destructive-foreground">
        <Lock className="size-4" />
        <span>Trial/subscription khatam — account <b>read-only</b> hai. Aapka data safe hai.</span>
        <Link href="/billing" className="font-semibold underline">Payment karke unlock karein</Link>
      </div>
    )
  }
  return null
}
