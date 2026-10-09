'use client'

import { useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Sparkles, Database } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { SourceBadges, EmptyState, Loading, Markdownish, PageHeader, Panel, PlatformBadge, Stat, can, errMsg, fmt, useMe } from '@/components/sg'

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good Morning' : h < 17 ? 'Good Afternoon' : 'Good Evening'
}

export default function Dashboard() {
  const me = useMe()
  const { data } = useApi('/analytics/overview', { days: 30 })
  const [insight, setInsight] = useState(null)
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)

  if (!data) return <Loading />

  const header = <PageHeader title={`${greeting()}, ${me.name}`} subtitle="Pichle 30 din ka overview" actions={<SourceBadges demo={data.hasDemo} live={data.hasLive} />} />

  if (data.accountCount === 0) {
    return (
      <>
        {header}
        <EmptyState
          title="Abhi koi social account connect nahi hai"
          text="Client → Project banayein, phir Social Accounts page se Instagram, Facebook ya YouTube connect karein. Ya product explore karne ke liye sample data load karein."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <ButtonLink href="/clients">Client banayein</ButtonLink>
              {can(me.role, 'admin') && (
                <Button
                  variant="outline"
                  disabled={seeding}
                  onClick={async () => {
                    setSeeding(true)
                    try {
                      await api.post('/demo-data')
                      toast.success('Demo data load ho gaya')
                      refreshAll()
                    } catch (e) {
                      toast.error(errMsg(e))
                    } finally {
                      setSeeding(false)
                    }
                  }}
                >
                  <Database className="size-4" /> {seeding ? 'Loading…' : 'Demo data load karein'}
                </Button>
              )}
            </div>
          }
        />
      </>
    )
  }

  const t = data.totals
  return (
    <>
      {header}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Followers" value={fmt(t.followers)} delta={data.deltas?.followers} hint={`${t.followerGrowth >= 0 ? '+' : ''}${fmt(t.followerGrowth)} in 30d`} />
        <Stat label="Engagement" value={`${t.engagementRate.toFixed(2)}%`} delta={data.deltas?.engagement} />
        <Stat label="Views" value={fmt(t.views)} delta={data.deltas?.views} />
        <Stat label="Likes" value={fmt(t.likes)} delta={data.deltas?.likes} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Panel title="Growth Analytics" className="lg:col-span-2" action={<Link href="/analytics" className="text-sm text-primary hover:underline">Details →</Link>}>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.chart} margin={{ left: 0, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="gF" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} stroke="var(--color-muted-foreground)" />
                <YAxis tickFormatter={(v) => fmt(v)} fontSize={11} width={48} stroke="var(--color-muted-foreground)" domain={['auto', 'auto']} />
                <Tooltip formatter={(v) => fmt(Number(v))} />
                <Area type="monotone" dataKey="followers" name="Followers" stroke="var(--color-chart-1)" strokeWidth={2} fill="url(#gF)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> AI Insight</span>}>
          {insight ? (
            <Markdownish text={insight} />
          ) : (
            <p className="text-sm text-muted-foreground">AI aapke last 30 din ke data ko analyse karke batayega kya kaam kar raha hai aur aage kya karna chahiye.</p>
          )}
          <Button
            className="mt-4 w-full"
            variant={insight ? 'outline' : 'default'}
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                const { data: r } = await api.post('/ai/insights', { days: 30 })
                setInsight(r.text)
                refreshAll()
              } catch (e) {
                toast.error(errMsg(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy ? 'Analysing…' : insight ? 'Refresh insight' : 'Generate insight'}
          </Button>
        </Panel>
      </div>

      <Panel title="Connected Platforms" className="mt-4" action={<Link href="/social-accounts" className="text-sm text-primary hover:underline">Manage →</Link>}>
        <div className="grid gap-3 sm:grid-cols-3">
          {data.perPlatform.map((p) => (
            <div key={p.platform} className="rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <PlatformBadge platform={p.platform} />
                <span className="text-xs font-medium text-success">● {p.accounts} connected</span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="text-lg font-bold">{fmt(p.followers)}</div>
                  <div className="text-[11px] text-muted-foreground">Followers</div>
                </div>
                <div>
                  <div className="text-lg font-bold">{p.engagementRate.toFixed(1)}%</div>
                  <div className="text-[11px] text-muted-foreground">Engagement</div>
                </div>
                <div>
                  <div className="text-lg font-bold">{fmt(p.views)}</div>
                  <div className="text-[11px] text-muted-foreground">Views</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </>
  )
}
