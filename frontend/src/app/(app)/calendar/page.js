'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, Plus, Sparkles, Trash2 } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Loading, PLATFORMS, P_LABEL, PageHeader, Panel, PlatformBadge, can, errMsg, selectClass, today, useMe } from '@/components/sg'

const STATUS_NEXT = { idea: 'scheduled', scheduled: 'published', published: 'idea' }
const STATUS_CLASS = { idea: 'border-l-muted-foreground', scheduled: 'border-l-primary', published: 'border-l-success' }

export default function CalendarPage() {
  const me = useMe()
  const [month, setMonth] = useState(today().slice(0, 7))
  const [clientId, setClientId] = useState('')
  const { data: items } = useApi('/content', { month, clientId })
  const { data: clients } = useApi('/clients')
  const client = clients?.find((c) => c.id === clientId)

  // remember the last client per browser; new items and AI plans default to it
  useEffect(() => {
    let saved = ''
    try { saved = localStorage.getItem('sg_cal_client') || '' } catch { /* storage blocked */ }
    if (saved) {
      setClientId(saved)
      setF((x) => ({ ...x, clientId: saved }))
      setAi((x) => ({ ...x, clientId: saved }))
    }
  }, [])
  function pickClient(id) {
    setClientId(id)
    setF((x) => ({ ...x, clientId: id }))
    setAi((x) => ({ ...x, clientId: id }))
    try { localStorage.setItem('sg_cal_client', id) } catch { /* storage blocked */ }
  }
  const [mode, setMode] = useState('none')
  const [f, setF] = useState({ date: today(), platform: 'instagram', format: 'Reel', topic: '', clientId: '' })
  const [ai, setAi] = useState({ topic: '', clientId: '', platforms: ['instagram'], startDate: today(), days: '30' })
  const [busy, setBusy] = useState(false)
  const edit = can(me.role, 'content')

  const [y, m] = month.split('-').map(Number)
  const first = new Date(Date.UTC(y, m - 1, 1))
  const daysIn = new Date(Date.UTC(y, m, 0)).getUTCDate()
  const lead = (first.getUTCDay() + 6) % 7
  const shift = (n) => setMonth(new Date(Date.UTC(y, m - 1 + n, 1)).toISOString().slice(0, 7))

  const act = (p) => p.then(refreshAll).catch((e) => toast.error(errMsg(e)))

  return (
    <>
      <PageHeader
        title={client ? `Content Calendar — ${client.name}` : 'Content Calendar'}
        subtitle="Har client ka apna calendar. Ideas → Scheduled → Published — card par click karke status badlein."
        actions={
          edit && (
            <>
              <Button variant="outline" onClick={() => setMode(mode === 'add' ? 'none' : 'add')}><Plus className="size-4" /> Add item</Button>
              <Button onClick={() => { setAi((x) => ({ ...x, clientId })); setMode(mode === 'ai' ? 'none' : 'ai') }} disabled={!me.limits.aiContent} title={me.limits.aiContent ? '' : 'Pro plan feature'}>
                <Sparkles className="size-4" /> AI plan{client ? ` — ${client.name}` : ''}
              </Button>
            </>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Client:</span>
        <button onClick={() => pickClient('')}
          className={`rounded-full border px-3 py-1 text-sm ${!clientId ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-muted'}`}>Sab clients</button>
        {clients?.map((c) => (
          <button key={c.id} onClick={() => pickClient(c.id)}
            className={`rounded-full border px-3 py-1 text-sm ${clientId === c.id ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-muted'}`}>{c.name}</button>
        ))}
      </div>

      {mode === 'add' && (
        <Panel title="Add content item" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6"
            onSubmit={async (e) => {
              e.preventDefault()
              try {
                await api.post('/content', { date: f.date, platform: f.platform, format: f.format, topic: f.topic, clientId: f.clientId || null })
                toast.success('Added')
                setF({ ...f, topic: '' })
                setMonth(f.date.slice(0, 7))
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              }
            }}
          >
            <Field label="Date"><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
            <Field label="Platform">
              <select className={selectClass} value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>
                {PLATFORMS.map((p) => <option key={p} value={p}>{P_LABEL[p]}</option>)}
              </select>
            </Field>
            <Field label="Format">
              <select className={selectClass} value={f.format} onChange={(e) => setF({ ...f, format: e.target.value })}>
                {['Reel', 'Carousel', 'Story', 'Image', 'Video', 'Short', 'Live'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </Field>
            <Field label="Client">
              <select className={selectClass} value={f.clientId} onChange={(e) => setF({ ...f, clientId: e.target.value })}>
                <option value="">—</option>
                {clients?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Topic"><Input required value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} /></Field>
            <div className="flex items-end"><Button type="submit">Add</Button></div>
          </form>
        </Panel>
      )}
      {mode === 'ai' && (
        <Panel title="AI content plan" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
            onSubmit={async (e) => {
              e.preventDefault()
              setBusy(true)
              try {
                const { data } = await api.post('/ai/calendar', { topic: ai.topic, platforms: ai.platforms, startDate: ai.startDate, days: Number(ai.days), clientId: ai.clientId || null })
                toast.success(`${data.count} ideas calendar mein add hue`)
                setMonth(ai.startDate.slice(0, 7))
                setMode('none')
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              } finally {
                setBusy(false)
              }
            }}
          >
            <Field label="Business / topic" hint={ai.clientId ? 'Khaali chhod sakte hain — AI client aur uske accounts ka data dekh kar plan banayega' : undefined}>
              <Input required={!ai.clientId} value={ai.topic} onChange={(e) => setAi({ ...ai, topic: e.target.value })} placeholder="Dental clinic in Lucknow" />
            </Field>
            <Field label="Client">
              <select className={selectClass} value={ai.clientId} onChange={(e) => setAi({ ...ai, clientId: e.target.value })}>
                <option value="">—</option>
                {clients?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="Start date"><Input type="date" value={ai.startDate} onChange={(e) => setAi({ ...ai, startDate: e.target.value })} /></Field>
            <Field label="Days"><Input type="number" min={7} max={31} value={ai.days} onChange={(e) => setAi({ ...ai, days: e.target.value })} /></Field>
            <Field label="Platforms">
              <div className="flex flex-wrap gap-3 pt-2">
                {PLATFORMS.map((p) => (
                  <label key={p} className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={ai.platforms.includes(p)} onChange={(e) => setAi({ ...ai, platforms: e.target.checked ? [...ai.platforms, p] : ai.platforms.filter((x) => x !== p) })} />
                    {P_LABEL[p]}
                  </label>
                ))}
              </div>
            </Field>
            <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-5">
              <Button type="submit" disabled={busy}><Sparkles className="size-4" /> {busy ? 'Plan ban raha hai… (30-60 sec)' : 'Generate plan'}</Button>
              <span className="text-xs text-muted-foreground">Dobara banane par isi client ke purane (sirf "Idea" wale) items un dino ke liye badal jayenge.</span>
            </div>
          </form>
        </Panel>
      )}

      <Panel
        title={first.toLocaleDateString('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })}
        action={
          <div className="flex gap-1">
            <Button size="sm" variant="outline" onClick={() => shift(-1)} aria-label="Previous month"><ChevronLeft className="size-4" /></Button>
            <Button size="sm" variant="outline" onClick={() => setMonth(today().slice(0, 7))}>Today</Button>
            <Button size="sm" variant="outline" onClick={() => shift(1)} aria-label="Next month"><ChevronRight className="size-4" /></Button>
          </div>
        }
      >
        {!items ? (
          <Loading />
        ) : (
          <div className="overflow-x-auto">
            <div className="grid min-w-[720px] grid-cols-7 gap-1">
              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="pb-1 text-center text-xs font-semibold text-muted-foreground">{d}</div>)}
              {Array.from({ length: lead }).map((_, i) => <div key={`l${i}`} />)}
              {Array.from({ length: daysIn }).map((_, i) => {
                const date = `${month}-${String(i + 1).padStart(2, '0')}`
                const dayItems = items.filter((x) => x.date === date)
                return (
                  <div key={date} className={`min-h-24 rounded-lg border p-1.5 ${date === today() ? 'border-primary bg-secondary/40' : 'bg-card'}`}>
                    <div className="text-xs font-semibold text-muted-foreground">{i + 1}</div>
                    <div className="mt-1 space-y-1">
                      {dayItems.map((it) => (
                        <div
                          key={it.id}
                          className={`group cursor-pointer rounded border-l-4 bg-muted/60 p-1 text-[11px] ${STATUS_CLASS[it.status]}`}
                          title={`${it.topic}${it.notes ? '\n' + it.notes : ''}${it.clientName ? '\nClient: ' + it.clientName : ''}\nStatus: ${it.status} (click to change)`}
                          onClick={() => edit && act(api.patch(`/content/${it.id}`, { status: STATUS_NEXT[it.status] }))}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <PlatformBadge platform={it.platform} label={false} />
                            <span className="font-semibold">{it.format}</span>
                            {edit && (
                              <button
                                aria-label="Delete"
                                className="hidden group-hover:block"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  act(api.delete(`/content/${it.id}`))
                                }}
                              >
                                <Trash2 className="size-3" />
                              </button>
                            )}
                          </div>
                          <div className="mt-0.5 line-clamp-2">{it.topic}</div>
                          {!clientId && it.clientName && <div className="mt-0.5 truncate text-[10px] font-semibold text-primary">{it.clientName}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
        <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
          <span>▍Idea</span><span className="text-primary">▍Scheduled</span><span className="text-success">▍Published</span>
        </div>
      </Panel>
    </>
  )
}
