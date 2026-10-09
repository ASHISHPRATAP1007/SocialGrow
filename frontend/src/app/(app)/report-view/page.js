'use client'

import { Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, Printer } from 'lucide-react'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Delta, EmptyState, Loading, Markdownish, PlatformBadge, fmt, niceDate } from '@/components/sg'

export default function ReportViewPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ReportView />
    </Suspense>
  )
}

function ReportView() {
  const id = useSearchParams().get('id') || ''
  const { data: report, error } = useApi(id ? `/reports/${id}` : null)
  if (!id) return <EmptyState title="Report nahi mili" text="Reports page se report kholein." />
  if (error) return <EmptyState title="Report nahi mili" text="Ye report delete ho chuki hai ya aapke workspace ki nahi hai." />
  if (!report) return <Loading />

  const data = JSON.parse(report.data)
  const color = report.brand.color

  return (
    <div>
      <div className="no-print mb-4 flex items-center justify-between">
        <ButtonLink variant="ghost" href="/reports"><ArrowLeft className="size-4" /> Reports</ButtonLink>
        <Button onClick={() => window.print()}><Printer className="size-4" /> Download PDF</Button>
      </div>
      <article className="print-area mx-auto max-w-4xl rounded-xl border bg-card p-8 shadow-sm sm:p-10">
        <header className="border-b-4 pb-6" style={color ? { borderColor: color } : undefined}>
          <div className="text-xl font-extrabold tracking-wide uppercase" style={color ? { color } : undefined}>{report.brand.name}</div>
          <h1 className="mt-4 text-3xl font-extrabold">Social Media Performance Report</h1>
          <div className="mt-3 grid gap-1 text-sm sm:grid-cols-3">
            <div><span className="text-muted-foreground">Client: </span><b>{report.clientName}</b></div>
            <div><span className="text-muted-foreground">Period: </span><b>{niceDate(report.periodStart)} – {niceDate(report.periodEnd)}</b></div>
            <div><span className="text-muted-foreground">Type: </span><b>{report.type}</b></div>
          </div>
          {data.accounts.some((a) => a.dataSource === 'demo data') && (
            <p className="mt-3 text-xs text-warning">Note: is report ke kuch accounts demo/sample data par based hain.</p>
          )}
        </header>

        <section className="mt-8 space-y-4">
          {data.accounts.map((a) => (
            <div key={a.platform + a.username} className="rounded-lg border p-4">
              <div className="mb-3 flex items-center gap-2">
                <PlatformBadge platform={a.platform} />
                <span className="text-sm font-semibold">@{a.username}</span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div><div className="text-xs text-muted-foreground">Followers</div><div className="text-lg font-bold">{fmt(a.current.followers)}</div><Delta value={a.change.followersPct} /></div>
                <div><div className="text-xs text-muted-foreground">Engagement</div><div className="text-lg font-bold">{a.current.engagementRate.toFixed(2)}%</div><Delta value={a.change.engagementPct} /></div>
                <div><div className="text-xs text-muted-foreground">Views</div><div className="text-lg font-bold">{fmt(a.current.views)}</div><Delta value={a.change.viewsPct} /></div>
                <div><div className="text-xs text-muted-foreground">New followers</div><div className="text-lg font-bold">{a.current.followerGrowth >= 0 ? '+' : ''}{fmt(a.current.followerGrowth)}</div></div>
              </div>
              {a.topPosts.length > 0 && (
                <div className="mt-4">
                  <div className="mb-1 text-xs font-semibold text-muted-foreground uppercase">Top performing content</div>
                  <ol className="list-decimal space-y-0.5 pl-5 text-sm">
                    {a.topPosts.slice(0, 3).map((p) => (
                      <li key={p.title + p.date}>{p.title} — {fmt(p.views)} views, {p.engagementRate}% engagement</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          ))}
        </section>

        <section className="mt-8">
          <h2 className="mb-2 text-lg font-bold" style={color ? { color } : undefined}>AI Insights & Recommendations</h2>
          <Markdownish text={report.aiSummary} />
        </section>

        <footer className="mt-10 border-t pt-4 text-center text-xs text-muted-foreground">
          {report.brand.footer || report.brand.name}
          {!report.brand.hidePoweredBy && <div className="mt-1">Powered by SocialGrow AI</div>}
        </footer>
      </article>
    </div>
  )
}
