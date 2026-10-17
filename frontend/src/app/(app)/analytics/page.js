'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApi } from '@/hooks/useApi'
import { SourceBadges, EmptyState, Loading, P_LABEL, PageHeader, Panel, PlatformBadge, Stat, fmt, selectClass } from '@/components/sg'
import { ClientPicker } from '@/components/client-picker'

const RANGES = [
  { label: '7 Days', days: 7 },
  { label: '30 Days', days: 30 },
  { label: '90 Days', days: 90 },
  { label: '6 Months', days: 182 },
  { label: '1 Year', days: 365 },
]

export default function AnalyticsPage() {
  const [days, setDays] = useState(30)
  const [platform, setPlatform] = useState('')
  const [clientId, setClientId] = useState('')
  const [accountId, setAccountId] = useState('')
  const { data: clients } = useApi('/clients')
  const { data: accounts } = useApi('/accounts')
  const { data } = useApi('/analytics/overview', { days, platform, clientId, accountId })

  return (
    <>
      <PageHeader title="Profile Analytics" subtitle="Followers, reach aur engagement — filter karke dekhein" actions={data ? <SourceBadges demo={data.hasDemo} live={data.hasLive} /> : undefined} />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <div className="flex rounded-lg border bg-card p-1">
          {RANGES.map((r) => (
            <button
              key={r.days}
              onClick={() => setDays(r.days)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold ${days === r.days ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'}`}
            >
              {r.label}
            </button>
          ))}
        </div>
        <ClientPicker className="w-52" clients={clients} value={clientId} allowAll onChange={(id) => { setClientId(id); setAccountId('') }} />
        <select className={selectClass + ' w-36'} value={platform} onChange={(e) => setPlatform(e.target.value)}>
          <option value="">All platforms</option>
          {['instagram', 'facebook', 'youtube'].map((p) => <option key={p} value={p}>{P_LABEL[p]}</option>)}
        </select>
        <select className={selectClass + ' w-48'} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">All accounts</option>
          {accounts
            ?.filter((a) => (!clientId || a.clientId === clientId) && (!platform || a.platform === platform))
            .map((a) => <option key={a.id} value={a.id}>{P_LABEL[a.platform]} · @{a.username}</option>)}
        </select>
      </div>
      {!data ? (
        <Loading />
      ) : data.accountCount === 0 ? (
        <EmptyState title="Data nahi mila" text="Is filter ke liye koi connected account nahi hai." />
      ) : (
        <>
          {data.quietAccounts?.length > 0 && (
            <div className="mb-3 rounded-md bg-warning-soft p-3 text-sm">
              Is range mein in accounts par koi nayi post nahi aayi, isliye numbers kam/zero dikh rahe hain:{' '}
              {data.quietAccounts.map((q, i) => (
                <span key={q.id}>
                  {i > 0 && ', '}
                  <Link href={`/account?id=${q.id}`} className="font-semibold text-primary hover:underline">@{q.username} ({P_LABEL[q.platform]})</Link>
                  {q.lastPostAt ? ` — aakhri post ${q.lastPostAt}` : ' — abhi koi post nahi'}
                </span>
              ))}
              . Naam par click karke <b>poori history</b> dekhein, ya upar badi range (1 Year) chunein.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <Stat label="Followers" value={fmt(data.totals.followers)} delta={data.deltas?.followers} />
            <Stat label="Growth" value={`${data.totals.followerGrowth >= 0 ? '+' : ''}${fmt(data.totals.followerGrowth)}`} hint={`${data.totals.growthRate.toFixed(2)}% growth rate`} />
            <Stat label="Engagement rate" value={`${data.totals.engagementRate.toFixed(2)}%`} delta={data.deltas?.engagement} />
            <Stat label="Views" value={fmt(data.totals.views)} delta={data.deltas?.views} />
            <Stat label="Posts" value={fmt(data.totals.posts)} />
            <Stat label="Likes" value={fmt(data.totals.likes)} delta={data.deltas?.likes} />
            <Stat label="Comments" value={fmt(data.totals.comments)} />
            <Stat label="Shares" value={fmt(data.totals.shares)} />
            <Stat label="Accounts" value={String(data.accountCount)} />
            <Stat label="Interactions" value={fmt(data.totals.likes + data.totals.comments + data.totals.shares)} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="Followers trend">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} />
                    <YAxis tickFormatter={(v) => fmt(v)} fontSize={11} width={48} domain={['auto', 'auto']} />
                    <Tooltip formatter={(v) => fmt(Number(v))} />
                    <Line type="monotone" dataKey="followers" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Views">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} />
                    <YAxis tickFormatter={(v) => fmt(v)} fontSize={11} width={48} />
                    <Tooltip formatter={(v) => fmt(Number(v))} />
                    <Bar dataKey="views" fill="var(--color-chart-2)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Daily engagement rate (%)" className="lg:col-span-2">
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.chart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} fontSize={11} />
                    <YAxis fontSize={11} width={40} />
                    <Tooltip />
                    <Line type="monotone" dataKey="engagement" stroke="var(--color-chart-3)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>

          <Panel title="By platform" className="mt-4">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground uppercase">
                  <tr><th className="py-2">Platform</th><th>Followers</th><th>Growth</th><th>Views</th><th>Engagement</th><th>Posts</th></tr>
                </thead>
                <tbody>
                  {data.perPlatform.map((p) => (
                    <tr key={p.platform} className="border-t">
                      <td className="py-2.5"><PlatformBadge platform={p.platform} /></td>
                      <td>{fmt(p.followers)}</td>
                      <td className={p.followerGrowth >= 0 ? 'text-success' : 'text-destructive'}>{p.growthRate.toFixed(2)}%</td>
                      <td>{fmt(p.views)}</td>
                      <td>{p.engagementRate.toFixed(2)}%</td>
                      <td>{p.posts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </>
  )
}
