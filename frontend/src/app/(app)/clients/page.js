'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2, Mail, Phone, Building2, Link2, MessageCircle } from 'lucide-react'
import { shareConnectLink, whatsappHref } from '@/components/connect'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, Field, Loading, PageHeader, Panel, PlatformBadge, can, errMsg, useMe } from '@/components/sg'

const EMPTY = { name: '', company: '', email: '', phone: '' }

export default function ClientsPage() {
  const me = useMe()
  const { data: clients } = useApi('/clients')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [links, setLinks] = useState({})
  const manage = can(me.role, 'manage')

  if (!clients) return <Loading />

  return (
    <>
      <PageHeader
        title="Clients"
        subtitle={`${clients.length} / ${me.limits.clients >= 1000 ? 'Unlimited' : me.limits.clients} clients (${me.limits.label} plan)`}
        actions={
          manage &&
          (clients.length >= me.limits.clients ? (
            <ButtonLink href="/billing" variant="outline">Limit reached — Upgrade</ButtonLink>
          ) : (
            <Button onClick={() => setOpen((o) => !o)}>
              <Plus className="size-4" /> New client
            </Button>
          ))
        }
      />
      {open && (
        <Panel title="New client" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={async (e) => {
              e.preventDefault()
              try {
                await api.post('/clients', { name: form.name, company: form.company || null, email: form.email || null, phone: form.phone || null })
                toast.success('Client add ho gaya')
                setForm(EMPTY)
                setOpen(false)
                refreshAll()
              } catch (err) {
                toast.error(errMsg(err))
              }
            }}
          >
            <Field label="Client name *">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="ABC Hospital" />
            </Field>
            <Field label="Company">
              <Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            </Field>
            <Field label="Email">
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Phone">
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit">Save client</Button>
              <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          </form>
        </Panel>
      )}
      {clients.length === 0 ? (
        <EmptyState title="Koi client nahi" text="Pehla client add karein. Har client ke andar projects aur social accounts honge." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {clients.map((c) => (
            <div key={c.id} className="rounded-xl border bg-card p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold">{c.name}</div>
                  {c.company && (
                    <div className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <Building2 className="size-3" /> {c.company}
                    </div>
                  )}
                </div>
                {manage && (
                  <button
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
                    aria-label="Delete client"
                    onClick={async () => {
                      if (!confirm(`${c.name} delete karein?`)) return
                      try {
                        await api.delete(`/clients/${c.id}`)
                        toast.success('Client delete hua')
                        refreshAll()
                      } catch (err) {
                        toast.error(errMsg(err))
                      }
                    }}
                  >
                    <Trash2 className="size-4" />
                  </button>
                )}
              </div>
              <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                {c.email && <div className="flex items-center gap-1.5"><Mail className="size-3" /> {c.email}</div>}
                {c.phone && <div className="flex items-center gap-1.5"><Phone className="size-3" /> {c.phone}</div>}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs font-medium">{c.projectCount} project(s)</span>
                {c.platforms.map((p) => <PlatformBadge key={p} platform={p} label={false} />)}
              </div>
              {manage && (
                <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
                  <Button size="sm" variant="outline" onClick={async () => {
                    const url = await shareConnectLink(c)
                    if (url) setLinks((l) => ({ ...l, [c.id]: url }))
                  }}>
                    <Link2 className="size-4" /> Connect link
                  </Button>
                  {links[c.id] && (
                    <a className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#25D366] px-3 text-sm font-medium text-white" href={whatsappHref(c, links[c.id])} target="_blank" rel="noreferrer">
                      <MessageCircle className="size-4" /> WhatsApp
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
