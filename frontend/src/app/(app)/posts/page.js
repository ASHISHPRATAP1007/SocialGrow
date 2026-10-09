'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Sparkles, X } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { EmptyState, Loading, P_LABEL, PageHeader, Panel, PlatformBadge, errMsg, fmt, niceDate, selectClass } from '@/components/sg'

export default function PostsPage() {
  const [days, setDays] = useState(90)
  const [platform, setPlatform] = useState('')
  const [sort, setSort] = useState('recent')
  const { data: posts } = useApi('/posts', { days, platform, sort })
  const [active, setActive] = useState(null)

  async function runAnalysis(id, title) {
    setActive({ id, title })
    try {
      const { data } = await api.post('/ai/analyze-post', { postId: id })
      setActive({ id, title, result: data })
      refreshAll()
    } catch (e) {
      toast.error(errMsg(e))
      setActive(null)
    }
  }

  return (
    <>
      <PageHeader title="Post Analytics" subtitle="Har post ka performance aur account average se comparison" />
      <div className="mb-4 flex flex-wrap gap-2">
        <select className={selectClass + ' w-36'} value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <select className={selectClass + ' w-36'} value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option value="">All platforms</option>
          {['instagram', 'facebook', 'youtube'].map((p) => <option key={p} value={p}>{P_LABEL[p]}</option>)}
        </select>
        <select className={selectClass + ' w-44'} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="recent">Most recent</option>
          <option value="views">Most views</option>
          <option value="engagement">Highest engagement</option>
        </select>
      </div>

      {active && (
        <Panel
          className="mb-4 border-primary/40"
          title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> AI Content Analysis — {active.title}</span>}
          action={<button onClick={() => setActive(null)} aria-label="Close"><X className="size-4" /></button>}
        >
          {!active.result ? (
            <Loading label="AI analyse kar raha hai…" />
          ) : (
            <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
              <div className="grid grid-cols-2 gap-2 text-sm">
                {['hook', 'clarity', 'cta', 'engagement'].map((k) => (
                  <div key={k} className="rounded-lg bg-muted/60 p-3">
                    <div className="text-[11px] font-semibold text-muted-foreground uppercase">{k === 'cta' ? 'CTA' : k}</div>
                    <div className="mt-0.5 font-semibold">{active.result[k] ?? '—'}</div>
                  </div>
                ))}
              </div>
              <div>
                {active.result.summary && <p className="text-sm">{active.result.summary}</p>}
                {!!active.result.suggestions?.length && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                    {active.result.suggestions.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                )}
              </div>
            </div>
          )}
        </Panel>
      )}

      {!posts ? (
        <Loading />
      ) : posts.length === 0 ? (
        <EmptyState title="Koi post nahi" text="Is period mein koi post data nahi mila." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {posts.map((p) => (
            <div key={p.id} className="flex flex-col rounded-xl border bg-card p-4 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <PlatformBadge platform={p.platform} />
                <span className="text-xs text-muted-foreground">{niceDate(p.publishedAt)}</span>
              </div>
              <div className="mt-2 font-semibold">
                {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-primary hover:underline">{p.title}</a> : p.title}
              </div>
              <div className="text-xs text-muted-foreground">@{p.username} · {p.format}{p.live ? ' · live' : ''}</div>
              <div className="mt-3 grid grid-cols-4 gap-1 text-center">
                {[['Views', p.views], ['Likes', p.likes], ['Comments', p.comments], ['Shares', p.shares]].map(([l, v]) => (
                  <div key={l}>
                    <div className="text-sm font-bold">{fmt(v)}</div>
                    <div className="text-[10px] text-muted-foreground">{l}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between border-t pt-3">
                <div className="text-xs">
                  Engagement <b>{p.engagementRate.toFixed(2)}%</b>
                  <span
                    className={`ml-2 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      p.performance === 'above' ? 'bg-success-soft text-success' : p.performance === 'below' ? 'bg-danger-soft text-destructive' : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {p.performance === 'above' ? 'Above avg' : p.performance === 'below' ? 'Below avg' : 'Average'}
                  </span>
                </div>
                <Button size="sm" variant="ghost" onClick={() => runAnalysis(p.id, p.title)}>
                  <Sparkles className="size-3.5" /> Analyze
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
