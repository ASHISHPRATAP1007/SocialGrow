'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Bot, Send, User } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { EmptyState, Markdownish, P_LABEL, PageHeader, Panel, errMsg, selectClass, useMe } from '@/components/sg'

const SUGGESTIONS = [
  'Why did my Instagram engagement decrease this month?',
  'Kaunsa content format sabse accha perform kar raha hai?',
  'Which platform is growing fastest and why?',
  'What should I post more of next month?',
]

export default function AnalystPage() {
  const me = useMe()
  const { data: accounts } = useApi('/accounts')
  const [q, setQ] = useState('')
  const [days, setDays] = useState(30)
  const [accountId, setAccountId] = useState('')
  const [msgs, setMsgs] = useState([])
  const [busy, setBusy] = useState(false)

  if (!me.limits.aiContent) {
    return (
      <>
        <PageHeader title="AI Growth Analyst" />
        <EmptyState title="Pro plan feature" text="AI Growth Analyst Pro aur Agency plans mein available hai." action={<ButtonLink href="/billing">Upgrade</ButtonLink>} />
      </>
    )
  }

  async function send(question) {
    if (!question.trim() || busy) return
    setMsgs((m) => [...m, { role: 'user', text: question }])
    setQ('')
    setBusy(true)
    try {
      const { data } = await api.post('/ai/analyst', { question, days, accountId: accountId || null })
      setMsgs((m) => [...m, { role: 'ai', text: data.text }])
      refreshAll()
    } catch (e) {
      toast.error(errMsg(e))
      setMsgs((m) => m.slice(0, -1))
      setQ(question)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="AI Growth Analyst" subtitle="Apne analytics ke baare mein kuch bhi poochiye — AI sirf aapke stored data se jawab deta hai." />
      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <Panel className="flex min-h-[60vh] flex-col">
          <div className="flex-1 space-y-4">
            {msgs.length === 0 && (
              <div className="py-8 text-center">
                <Bot className="mx-auto size-10 text-primary" />
                <p className="mt-2 text-sm text-muted-foreground">Ek sawal chunein ya apna likhein:</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-full border px-3 py-1.5 text-xs hover:border-primary hover:text-primary">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : ''}`}>
                {m.role === 'ai' && <div className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground"><Bot className="size-4" /></div>}
                <div className={`max-w-[85%] rounded-xl px-4 py-3 ${m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted/60'}`}>
                  {m.role === 'ai' ? <Markdownish text={m.text} /> : <p className="text-sm">{m.text}</p>}
                </div>
                {m.role === 'user' && <div className="grid size-8 shrink-0 place-items-center rounded-full bg-muted"><User className="size-4" /></div>}
              </div>
            ))}
            {busy && <div className="text-sm text-muted-foreground">AI data analyse kar raha hai…</div>}
          </div>
          <form
            className="mt-4 flex gap-2 border-t pt-4"
            onSubmit={(e) => {
              e.preventDefault()
              void send(q)
            }}
          >
            <Textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. Is mahine engagement kyun kam hua?"
              rows={2}
              className="resize-none"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(q)
                }
              }}
            />
            <Button type="submit" disabled={busy || !q.trim()} className="self-end" aria-label="Send">
              <Send className="size-4" />
            </Button>
          </form>
        </Panel>
        <Panel title="Context">
          <div className="space-y-3 text-sm">
            <label className="block space-y-1">
              <span className="text-xs font-medium">Period</span>
              <select className={selectClass} value={days} onChange={(e) => setDays(Number(e.target.value))}>
                <option value={7}>Last 7 days</option>
                <option value={30}>Last 30 days</option>
                <option value={90}>Last 90 days</option>
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-xs font-medium">Account</span>
              <select className={selectClass} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">All accounts</option>
                {accounts?.map((a) => <option key={a.id} value={a.id}>{P_LABEL[a.platform]} · @{a.username}</option>)}
              </select>
            </label>
            <p className="text-xs text-muted-foreground">Har sawal 1 AI credit use karta hai. Is mahine: {me.aiUsed} / {me.limits.aiPerMonth}.</p>
          </div>
        </Panel>
      </div>
    </>
  )
}
