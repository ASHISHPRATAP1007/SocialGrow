'use client'

import { Suspense, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, ExternalLink, MessageSquare, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { DemoBadge, EmptyState, LiveBadge, Loading, P_LABEL, PageHeader, Panel, PlatformBadge, Stat, can, errMsg, fmt, niceDate, useMe } from '@/components/sg'

/** Full picture of one account — no date range, so quiet accounts still show everything. */
export default function AccountPage() {
  return (
    <Suspense fallback={<Loading />}>
      <AccountView />
    </Suspense>
  )
}

const LABEL = { youtube: ['Subscribers', 'Videos'], instagram: ['Followers', 'Posts'], facebook: ['Followers', 'Posts'] }

function PostRow({ p, internal }) {
  const title = internal
    ? <Link href={`/post?id=${p.id}`} className="font-medium hover:text-primary hover:underline">▶ {p.title}</Link>
    : p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="font-medium hover:text-primary hover:underline">{p.title}</a> : <span className="font-medium">{p.title}</span>
  return (
    <tr className="border-t align-top">
      <td className="py-2.5 pr-3">
        {title}
        <div className="text-[11px] text-muted-foreground">{niceDate(p.publishedAt)} · {p.format}</div>
      </td>
      <td className="px-2 text-right">{fmt(p.views)}</td>
      <td className="px-2 text-right">{fmt(p.likes)}</td>
      <td className="px-2 text-right">
        {internal ? (
          <Link href={`/post?id=${p.id}`} className="inline-flex items-center gap-1 text-primary hover:underline">
            <MessageSquare className="size-3.5" /> {fmt(p.comments)}
          </Link>
        ) : fmt(p.comments)}
      </td>
      <td className="px-2 text-right">{fmt(p.shares)}</td>
      <td className="pl-2 text-right">{p.engagementRate.toFixed(2)}%</td>
    </tr>
  )
}

function AccountView() {
  const id = useSearchParams().get('id')
  const me = useMe()
  const { data, error } = useApi(id ? `/accounts/${id}/details` : null)
  const [syncing, setSyncing] = useState(false)
  const [showAll, setShowAll] = useState(false)

  if (!id) return <EmptyState title="Account chunein" text="Social Accounts page se kisi account par click karein." />
  if (error) return <EmptyState title="Account nahi mila" text={errMsg(error)} />
  if (!data) return <Loading />

  const { account: a, lifetime: l } = data
  const [fLabel, pLabel] = LABEL[a.platform]
  const posts = showAll ? data.posts : data.posts.slice(0, 15)

  return (
    <>
      <Link href="/social-accounts" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary">
        <ArrowLeft className="size-4" /> Social Accounts
      </Link>
      <PageHeader
        title={<span className="flex flex-wrap items-center gap-2"><PlatformBadge platform={a.platform} label={false} /> {a.displayName || a.username}</span>}
        subtitle={`@${a.username} · ${P_LABEL[a.platform]}${a.clientName ? ` · Client: ${a.clientName}` : ''}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {a.mode === 'api' ? <LiveBadge /> : <DemoBadge />}
            {a.url && (
              <a href={a.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1 rounded-md border px-3 text-sm hover:bg-muted">
                Open profile <ExternalLink className="size-3.5" />
              </a>
            )}
            {a.mode === 'api' && can(me.role, 'manage') && (
              <Button size="sm" variant="outline" disabled={syncing} onClick={async () => {
                setSyncing(true)
                try {
                  const { data: r } = await api.post(`/accounts/${a.id}/sync`)
                  if (r.error) toast.error(r.error)
                  else toast.success('Latest data aa gaya')
                  refreshAll()
                } catch (e) {
                  toast.error(errMsg(e))
                } finally {
                  setSyncing(false)
                }
              }}>
                <RefreshCw className={`size-4 ${syncing ? 'animate-spin' : ''}`} /> Sync now
              </Button>
            )}
          </div>
        }
      />

      {a.syncError && <p className="mb-3 rounded-md bg-warning-soft p-3 text-xs">Last sync error: {a.syncError}</p>}
      {l.daysSinceLastPost != null && l.daysSinceLastPost > 30 && (
        <p className="mb-3 rounded-md bg-warning-soft p-3 text-sm">
          ⏸️ Is account par <b>{l.daysSinceLastPost} din</b> se koi nayi post nahi aayi (aakhri: {niceDate(l.lastPostAt)}).
          Isliye Analytics ki 30/90 din wali range khaali dikhti hai — neeche poori history hai.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label={fLabel} value={fmt(a.followers)} />
        {a.totalViews != null && <Stat label="Total channel views" value={fmt(a.totalViews)} />}
        <Stat label={`${pLabel} (synced)`} value={fmt(l.posts)} hint={l.firstPostAt ? `${niceDate(l.firstPostAt)} se` : undefined} />
        <Stat label="Engagement rate" value={`${l.engagementRate.toFixed(2)}%`} hint="likes+comments+shares / views" />
        <Stat label="Views (in posts)" value={fmt(l.views)} hint={`avg ${fmt(l.avgViews)} / post`} />
        <Stat label="Likes" value={fmt(l.likes)} hint={`avg ${fmt(l.avgLikes)} / post`} />
        <Stat label="Comments" value={fmt(l.comments)} hint={`avg ${l.avgComments.toFixed(1)} / post`} />
        <Stat label="Last post" value={l.lastPostAt ? niceDate(l.lastPostAt) : '—'} />
      </div>

      {data.posts.length === 0 ? (
        <EmptyState title="Abhi koi post nahi" text="Is account par post aate hi agle sync mein yahan dikhegi." />
      ) : (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="Har mahine — posts aur views">
              <div className="h-60">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.monthly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="month" fontSize={11} />
                    <YAxis tickFormatter={(v) => fmt(v)} fontSize={11} width={48} />
                    <Tooltip formatter={(v) => fmt(Number(v))} />
                    <Bar dataKey="views" name="Views" fill="var(--color-chart-2)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Kaunsa format best chalta hai">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground uppercase">
                  <tr><th className="py-2">Format</th><th className="text-right">Posts</th><th className="text-right">Avg views</th><th className="text-right">Avg engagement</th></tr>
                </thead>
                <tbody>
                  {data.formats.map((f) => (
                    <tr key={f.format} className="border-t">
                      <td className="py-2">{f.format}</td>
                      <td className="text-right">{f.posts}</td>
                      <td className="text-right">{fmt(f.avgViews)}</td>
                      <td className="text-right">{f.avgEngagement.toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.history.length > 1 && (
                <div className="mt-4 h-32">
                  <div className="mb-1 text-xs text-muted-foreground">{fLabel} trend (connect ke din se)</div>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data.history}>
                      <XAxis dataKey="date" hide />
                      <YAxis hide domain={['auto', 'auto']} />
                      <Tooltip formatter={(v) => fmt(Number(v))} />
                      <Line type="monotone" dataKey="followers" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Panel>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {[['🏆 Sabse zyada views', data.bestByViews, (p) => `${fmt(p.views)} views`], ['🔥 Sabse zyada engagement', data.bestByEngagement, (p) => `${p.engagementRate.toFixed(2)}%`]].map(([title, list, val]) => (
              <Panel key={title} title={title}>
                <ol className="space-y-2 text-sm">
                  {list.map((p, i) => (
                    <li key={p.id} className="flex items-start justify-between gap-3">
                      <span className="min-w-0"><b className="mr-1 text-muted-foreground">{i + 1}.</b>
                        {data.commentsSupported ? <Link href={`/post?id=${p.id}`} className="hover:text-primary hover:underline">{p.title}</Link>
                          : p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="hover:text-primary hover:underline">{p.title}</a> : p.title}
                        <span className="ml-1 text-[11px] text-muted-foreground">{niceDate(p.publishedAt)}</span>
                      </span>
                      <span className="shrink-0 font-semibold">{val(p)}</span>
                    </li>
                  ))}
                </ol>
              </Panel>
            ))}
          </div>

          <Panel title={`Saari ${pLabel.toLowerCase()} (${data.posts.length})`} className="mt-4">
            {data.commentsSupported && <p className="-mt-1 mb-2 text-xs text-muted-foreground">Video par click karein — wahin play hogi, saare comments dikhenge, reply aur share kar sakte hain.</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground uppercase">
                  <tr><th className="py-2">Post</th><th className="px-2 text-right">Views</th><th className="px-2 text-right">Likes</th><th className="px-2 text-right">Comments</th><th className="px-2 text-right">Shares</th><th className="pl-2 text-right">Eng.</th></tr>
                </thead>
                <tbody>
                  {posts.map((p) => <PostRow key={p.id} p={p} internal={data.commentsSupported} />)}
                </tbody>
              </table>
            </div>
            {data.posts.length > 15 && (
              <Button variant="ghost" size="sm" className="mt-2" onClick={() => setShowAll((s) => !s)}>
                {showAll ? 'Kam dikhayein' : `Saari ${data.posts.length} dikhayein`}
              </Button>
            )}
          </Panel>
        </>
      )}
    </>
  )
}
