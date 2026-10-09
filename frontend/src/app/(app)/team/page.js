'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { UserPlus, Trash2, Check, Minus } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, Loading, PageHeader, Panel, ROLE_LABEL, can, errMsg, selectClass, useMe } from '@/components/sg'

const ROLES = ['admin', 'manager', 'analyst', 'content_manager', 'viewer']

const MATRIX = [
  ['View Analytics', ['owner', 'admin', 'manager', 'analyst', 'content_manager', 'viewer']],
  ['Manage Clients & Projects', ['owner', 'admin', 'manager']],
  ['Manage Social Accounts', ['owner', 'admin', 'manager']],
  ['Content & Calendar', ['owner', 'admin', 'manager', 'content_manager']],
  ['Generate Reports', ['owner', 'admin', 'manager', 'analyst']],
  ['Team & Settings', ['owner', 'admin']],
  ['Billing', ['owner']],
]

export default function TeamPage() {
  const me = useMe()
  const { data: members } = useApi('/members')
  const [f, setF] = useState({ email: '', name: '', role: 'analyst' })
  const admin = can(me.role, 'admin')

  if (!members) return <Loading />

  const act = (p, ok) =>
    p.then(() => {
      if (ok) toast.success(ok)
      refreshAll()
    }).catch((e) => toast.error(errMsg(e)))

  return (
    <>
      <PageHeader title="Team Members" subtitle={`${members.length} / ${me.limits.members} seats (${me.limits.label} plan)`} />
      {admin && (
        <Panel title="Invite member" className="mb-4">
          <form
            className="grid gap-3 sm:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              act(
                api.post('/members', { email: f.email, name: f.name || null, role: f.role }).then(() => setF({ ...f, email: '', name: '' })),
                'Invite add ho gaya. Wo isi email se sign up karke team join kar lenge.',
              )
            }}
          >
            <Field label="Email"><Input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
            <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Role">
              <select className={selectClass} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </Field>
            <div className="flex items-end"><Button type="submit"><UserPlus className="size-4" /> Invite</Button></div>
          </form>
        </Panel>
      )}
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="overflow-x-auto rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-xs text-muted-foreground uppercase">
              <tr><th className="px-4 py-3">Member</th><th className="px-4 py-3">Role</th><th className="px-4 py-3">Status</th><th /></tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id} className="border-t">
                  <td className="px-4 py-3"><div className="font-medium">{m.name || m.email.split('@')[0]}</div><div className="text-xs text-muted-foreground">{m.email}</div></td>
                  <td className="px-4 py-3">
                    {m.role === 'owner' || !admin ? (
                      <span className="font-medium">{ROLE_LABEL[m.role]}</span>
                    ) : (
                      <select className={selectClass + ' h-8 w-40'} value={m.role} onChange={(e) => act(api.patch(`/members/${m.id}`, { role: e.target.value }))}>
                        {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-3"><span className={`text-xs font-semibold ${m.status === 'active' ? 'text-success' : 'text-warning'}`}>{m.status === 'active' ? 'Active' : 'Invited'}</span></td>
                  <td className="px-4 py-3 text-right">
                    {admin && m.role !== 'owner' && (
                      <button aria-label="Remove" className="text-muted-foreground hover:text-destructive" onClick={() => confirm('Member remove karein?') && act(api.delete(`/members/${m.id}`))}>
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Panel title="Role permissions">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="py-1 text-left" />
                  {['owner', ...ROLES].map((r) => <th key={r} className="px-1 py-1 font-semibold">{ROLE_LABEL[r].split(' ')[0]}</th>)}
                </tr>
              </thead>
              <tbody>
                {MATRIX.map(([perm, roles]) => (
                  <tr key={perm} className="border-t">
                    <td className="py-1.5 pr-2">{perm}</td>
                    {['owner', ...ROLES].map((r) => (
                      <td key={r} className="text-center">{roles.includes(r) ? <Check className="mx-auto size-3.5 text-success" /> : <Minus className="mx-auto size-3.5 text-muted-foreground/40" />}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  )
}
