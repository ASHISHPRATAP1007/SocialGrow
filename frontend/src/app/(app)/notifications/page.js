'use client'

import { Bell, CheckCheck } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { EmptyState, Loading, PageHeader } from '@/components/sg'

export default function NotificationsPage() {
  const { data: items } = useApi('/notifications')
  if (!items) return <Loading />
  return (
    <>
      <PageHeader
        title="Notifications"
        actions={items.some((n) => !n.read) && <Button variant="outline" onClick={() => api.post('/notifications/read-all').then(refreshAll)}><CheckCheck className="size-4" /> Mark all read</Button>}
      />
      {items.length === 0 ? (
        <EmptyState title="Sab clear hai" text="Reports, campaigns, goals aur team updates yahan dikhenge." />
      ) : (
        <div className="divide-y rounded-xl border bg-card shadow-sm">
          {items.map((n) => (
            <div key={n.id} className={`flex items-start gap-3 px-4 py-3 ${n.read ? '' : 'bg-secondary/40'}`}>
              <Bell className={`mt-0.5 size-4 shrink-0 ${n.read ? 'text-muted-foreground' : 'text-primary'}`} />
              <div className="flex-1">
                <div className={`text-sm ${n.read ? '' : 'font-semibold'}`}>{n.text}</div>
                <div className="text-xs text-muted-foreground">{new Date(n.createdAt).toLocaleString('en-IN')} · {n.kind}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
