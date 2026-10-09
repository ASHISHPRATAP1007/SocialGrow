'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Sparkles, Copy } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { Button, ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, Field, Loading, PLATFORMS, P_LABEL, PageHeader, Panel, errMsg, selectClass, useMe } from '@/components/sg'

const SECTIONS = [
  ['hooks', 'Hooks'],
  ['captions', 'Captions'],
  ['cta', 'Call to action'],
  ['contentIdeas', 'Content ideas'],
  ['reelIdeas', 'Reel / Short ideas'],
  ['carouselIdeas', 'Carousel ideas'],
]

export default function ContentAI() {
  const me = useMe()
  const [f, setF] = useState({ platform: 'instagram', topic: '', audience: '18-35, local city', tone: 'Professional', language: 'English' })
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)

  if (!me.limits.aiContent) {
    return (
      <>
        <PageHeader title="AI Content Assistant" />
        <EmptyState title="Pro plan feature" text="AI Content tools Pro aur Agency plans mein available hain." action={<ButtonLink href="/billing">Upgrade</ButtonLink>} />
      </>
    )
  }

  const copy = (t) => {
    void navigator.clipboard.writeText(t)
    toast.success('Copied')
  }

  return (
    <>
      <PageHeader title="AI Content Assistant" subtitle="Suggestions hain — review karke hi publish karein." />
      <Panel className="mb-4">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            setOut(null)
            try {
              const { data } = await api.post('/ai/content', f)
              setOut(data)
              refreshAll()
            } catch (err) {
              toast.error(errMsg(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          <Field label="Platform">
            <select className={selectClass} value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>
              {PLATFORMS.map((p) => <option key={p} value={p}>{P_LABEL[p]}</option>)}
            </select>
          </Field>
          <Field label="Topic / Business">
            <Input required value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} placeholder="Dental Clinic" />
          </Field>
          <Field label="Audience">
            <Input value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} />
          </Field>
          <Field label="Tone">
            <select className={selectClass} value={f.tone} onChange={(e) => setF({ ...f, tone: e.target.value })}>
              {['Professional', 'Friendly', 'Fun', 'Inspirational', 'Educational'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Language">
            <select className={selectClass} value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}>
              {['English', 'Hinglish', 'Hindi'].map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <div className="sm:col-span-2 lg:col-span-5">
            <Button type="submit" disabled={busy}>
              <Sparkles className="size-4" /> {busy ? 'Generating…' : 'Generate content'}
            </Button>
          </div>
        </form>
      </Panel>
      {busy && <Loading label="AI content likh raha hai…" />}
      {out && (
        <div className="grid gap-4 md:grid-cols-2">
          {SECTIONS.filter(([k]) => out[k]?.length).map(([k, label]) => (
            <Panel key={k} title={label}>
              <ul className="space-y-2">
                {out[k].map((t, i) => (
                  <li key={i} className="group flex items-start justify-between gap-2 rounded-lg bg-muted/50 p-3 text-sm">
                    <span className="whitespace-pre-wrap">{t}</span>
                    <button aria-label="Copy" onClick={() => copy(t)} className="opacity-50 hover:opacity-100"><Copy className="size-3.5" /></button>
                  </li>
                ))}
              </ul>
            </Panel>
          ))}
          {!!out.hashtags?.length && (
            <Panel title="Hashtag suggestions" action={<Button size="sm" variant="ghost" onClick={() => copy(out.hashtags.join(' '))}><Copy className="size-3.5" /> Copy all</Button>}>
              <div className="flex flex-wrap gap-2">
                {out.hashtags.map((h) => <span key={h} className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">{h}</span>)}
              </div>
            </Panel>
          )}
        </div>
      )}
    </>
  )
}
