'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  LayoutDashboard, Users, FolderKanban, Link2, BarChart3, FileImage, Target, Megaphone, Sparkles, CalendarDays, Bot, FileText,
  UserCog, CreditCard, Settings, Bell, Shield, LogOut, Menu, X, ChevronDown,
} from 'lucide-react'
import { getToken, signOut } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Loading, MeContext, ROLE_LABEL } from '@/components/sg'
import { AccessBanner, AccessGate } from '@/components/access'
import { cn } from '@/lib/utils'

const NAV = [
  {
    group: 'Analytics',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { to: '/analytics', label: 'Analytics', icon: BarChart3 },
      { to: '/posts', label: 'Posts', icon: FileImage },
      { to: '/goals', label: 'Growth Goals', icon: Target },
    ],
  },
  {
    group: 'Agency',
    items: [
      { to: '/clients', label: 'Clients', icon: Users },
      { to: '/projects', label: 'Projects', icon: FolderKanban },
      { to: '/social-accounts', label: 'Social Accounts', icon: Link2 },
      { to: '/campaigns', label: 'Campaigns', icon: Megaphone },
      { to: '/reports', label: 'Reports', icon: FileText },
    ],
  },
  {
    group: 'AI',
    items: [
      { to: '/ai-analyst', label: 'AI Growth Analyst', icon: Bot },
      { to: '/content-ai', label: 'AI Content', icon: Sparkles },
      { to: '/calendar', label: 'Content Calendar', icon: CalendarDays },
    ],
  },
  {
    group: 'Workspace',
    items: [
      { to: '/team', label: 'Team', icon: UserCog },
      { to: '/billing', label: 'Billing', icon: CreditCard },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
]

export default function AppLayout({ children }) {
  const router = useRouter()
  const [hasToken, setHasToken] = useState(null)

  useEffect(() => {
    const t = !!getToken()
    setHasToken(t)
    if (!t) router.replace('/')
  }, [router])

  const { data: me, error } = useApi(hasToken ? '/me' : null, null, { refreshInterval: 30000 })

  if (!hasToken || (!me && !error)) return <Loading />
  if (error) return <Loading label="Server se connect ho raha hai…" />
  if (['pending', 'rejected', 'suspended'].includes(me.access.state) && !me.isPlatformAdmin) return <AccessGate me={me} />
  return (
    <MeContext.Provider value={me}>
      <Shell me={me}>{children}</Shell>
    </MeContext.Provider>
  )
}

function Shell({ me, children }) {
  const path = usePathname()
  const [open, setOpen] = useState(false)
  useEffect(() => setOpen(false), [path])

  const groups = [...NAV, ...(me.isPlatformAdmin ? [{ group: 'Platform', items: [{ to: '/admin', label: 'Admin Panel', icon: Shield }] }] : [])]
  const activeGroup = groups.find((g) => g.items.some((it) => it.to === path))?.group ?? 'Analytics'
  const [openGroups, setOpenGroups] = useState([activeGroup])
  useEffect(() => {
    setOpenGroups((prev) => (prev.includes(activeGroup) ? prev : [...prev, activeGroup]))
  }, [activeGroup])
  const toggleGroup = (name) => setOpenGroups((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]))

  const sidebar = (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-5 py-3.5">
        <div className="grid size-8 place-items-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-extrabold text-sidebar-accent-foreground">{me.agency.brandName || 'SocialGrow AI'}</div>
          <div className="truncate text-[11px] opacity-70">{me.agency.name}</div>
        </div>
      </div>
      <nav className="no-scrollbar flex-1 space-y-1 overflow-y-auto px-3 pb-3">
        {groups.map((g) => {
          const isOpen = openGroups.includes(g.group)
          const hasActive = g.items.some((it) => it.to === path)
          return (
            <div key={g.group}>
              <button
                type="button"
                onClick={() => toggleGroup(g.group)}
                aria-expanded={isOpen}
                className={cn(
                  'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-[11px] font-bold tracking-widest uppercase hover:bg-sidebar-accent',
                  hasActive ? 'text-sidebar-accent-foreground' : 'opacity-60',
                )}
              >
                {g.group}
                <ChevronDown className={cn('size-3.5 transition-transform', isOpen ? 'rotate-180' : '')} />
              </button>
              {isOpen && (
                <div className="mt-0.5 mb-1.5 space-y-0.5">
                  {g.items.map((it) => {
                    const active = path === it.to
                    return (
                      <Link
                        key={it.to}
                        href={it.to}
                        className={cn(
                          'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                          active ? 'bg-sidebar-primary font-semibold text-sidebar-primary-foreground' : 'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                        )}
                      >
                        <it.icon className="size-4" />
                        {it.label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>
      <div className="flex items-center gap-2 border-t border-sidebar-border px-3 py-2.5">
        <div className="min-w-0 flex-1 px-1 text-xs">
          <div className="truncate font-semibold text-sidebar-accent-foreground">{me.email}</div>
          <div className="truncate opacity-70">
            {ROLE_LABEL[me.role]} · {me.limits.label} plan
          </div>
        </div>
        <button onClick={signOut} title="Sign out" aria-label="Sign out" className="rounded-lg p-2 hover:bg-sidebar-accent">
          <LogOut className="size-4" />
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-background lg:pl-64">
      <aside className="no-print fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>
      {open && (
        <div className="no-print fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-foreground/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72">{sidebar}</div>
        </div>
      )}
      <header className="no-print sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-card/90 px-4 backdrop-blur">
        <button className="lg:hidden" onClick={() => setOpen((o) => !o)} aria-label="Menu">
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
        <div className="hidden text-sm text-muted-foreground lg:block">
          AI usage: <span className="font-semibold text-foreground">{me.aiUsed}</span> / {me.limits.aiPerMonth} this month
        </div>
        <Link href="/notifications" className="relative rounded-full p-2 hover:bg-muted" aria-label="Notifications">
          <Bell className="size-5" />
          {me.unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
              {me.unread > 99 ? '99+' : me.unread}
            </span>
          )}
        </Link>
      </header>
      <AccessBanner me={me} />
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
    </div>
  )
}
