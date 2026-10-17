'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button, ButtonLink } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, Field, Loading, PLATFORMS, P_LABEL, PageHeader, Panel, PlatformBadge, addDays, can, errMsg, niceDate, selectClass, today, useMe } from '@/components/sg'
import { ClientPicker } from '@/components/client-picker'

export default function ProjectsPage() {
  const me = useMe()
  const { data: projects } = useApi('/projects')
  const { data: clients } = useApi('/clients')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ clientId: '', name: '', platforms: ['instagram'], startDate: today(), endDate: addDays(today(), 30) })
  const manage = can(me.role, 'manage')

  if (!projects || !clients) return <Loading />

  const act = async (fn, ok) => {
    try {
      await fn()
      if (ok) toast.success(ok)
      refreshAll()
    } catch (err) {
      toast.error(errMsg(err))
    }
  }

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={`${projects.length} / ${me.limits.projects >= 5000 ? 'Unlimited' : me.limits.projects} projects`}
        actions={
          manage &&
          (projects.length >= me.limits.projects ? (
            <ButtonLink href="/billing" variant="outline">Limit reached — Upgrade</ButtonLink>
          ) : (
            <Button onClick={() => setOpen((o) => !o)} disabled={clients.length === 0}>
              <Plus className="size-4" /> New project
            </Button>
          ))
        }
      />
      {clients.length === 0 && (
        <EmptyState title="Pehle client banayein" text="Har project ek client ke under hota hai." action={<ButtonLink href="/clients">Clients page</ButtonLink>} />
      )}
      {open && (
        <Panel title="New project" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={async (e) => {
              e.preventDefault()
              if (!form.clientId) return toast.error('Client chunein')
              await act(async () => {
                await api.post('/projects', form)
                setOpen(false)
                setForm({ ...form, name: '' })
              }, 'Project ban gaya')
            }}
          >
            <Field label="Client *">
              <ClientPicker clients={clients} value={form.clientId} onChange={(id) => setForm({ ...form, clientId: id })} />
            </Field>
            <Field label="Project name *">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="ABC Hospital Social Growth" />
            </Field>
            <Field label="Start date">
              <Input type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} />
            </Field>
            <Field label="End date">
              <Input type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} />
            </Field>
            <Field label="Platforms">
              <div className="flex flex-wrap gap-3 pt-1">
                {PLATFORMS.map((p) => (
                  <label key={p} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={form.platforms.includes(p)}
                      onChange={(e) => setForm({ ...form, platforms: e.target.checked ? [...form.platforms, p] : form.platforms.filter((x) => x !== p) })}
                    />
                    {P_LABEL[p]}
                  </label>
                ))}
              </div>
            </Field>
            <div className="flex items-end gap-2">
              <Button type="submit">Create project</Button>
              <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          </form>
        </Panel>
      )}
      {projects.length === 0 && clients.length > 0 ? (
        <EmptyState title="Koi project nahi" text="Ek project banayein, jaise 'Instagram Growth' ya 'Brand Awareness'." />
      ) : (
        projects.length > 0 && (
          <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-xs text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-3">Project</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Platforms</th>
                  <th className="px-4 py-3">Period</th>
                  <th className="px-4 py-3">Accounts</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id} className="border-t">
                    <td className="px-4 py-3 font-medium">{p.name}</td>
                    <td className="px-4 py-3">{p.clientName}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">{p.platforms.map((x) => <PlatformBadge key={x} platform={x} label={false} />)}</div>
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">{niceDate(p.startDate)} – {niceDate(p.endDate)}</td>
                    <td className="px-4 py-3">{p.accountCount}</td>
                    <td className="px-4 py-3">
                      <select
                        className={selectClass + ' h-8 w-28'}
                        value={p.status}
                        disabled={!manage}
                        onChange={(e) => act(() => api.patch(`/projects/${p.id}`, { status: e.target.value }))}
                      >
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                        <option value="completed">Completed</option>
                      </select>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {manage && (
                        <button
                          className="rounded p-1 text-muted-foreground hover:text-destructive"
                          aria-label="Delete project"
                          onClick={() => confirm('Project delete karein?') && act(() => api.delete(`/projects/${p.id}`))}
                        >
                          <Trash2 className="size-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </>
  )
}
