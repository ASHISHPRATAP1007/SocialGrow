'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { CheckCircle2, Upload } from 'lucide-react'
import { api, refreshAll } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Field, Panel, errMsg, selectClass } from '@/components/sg'

const EMPTY = { title: '', description: '', tags: '', privacy: 'public', schedule: '', madeForKids: false }

function mb(n) {
  return n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`
}

/** Upload a video to the connected YouTube channel. The file goes straight from the browser to YouTube. */
export function YoutubeUpload({ accountId }) {
  const { data: st } = useApi(`/accounts/${accountId}/youtube/upload-status`)
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState(null)
  const [f, setF] = useState(EMPTY)
  const [progress, setProgress] = useState(null)
  const [done, setDone] = useState(null)
  const xhr = useRef(null)

  if (!st?.youtube) return null

  async function submit(e) {
    e.preventDefault()
    if (!file) return toast.error('Video file chunein')
    setDone(null)
    setProgress(0)
    try {
      const { data } = await api.post(`/accounts/${accountId}/youtube/upload-session`, {
        title: f.title, description: f.description, tags: f.tags.split(',').map((t) => t.trim()).filter(Boolean),
        privacy: f.privacy, publishAt: f.schedule ? new Date(f.schedule).toISOString() : null, madeForKids: f.madeForKids,
        size: file.size, mimeType: file.type || 'video/mp4',
      })
      const video = await new Promise((resolve, reject) => {
        const x = new XMLHttpRequest()
        xhr.current = x
        x.open('PUT', data.uploadUrl)
        x.setRequestHeader('Content-Type', file.type || 'video/mp4')
        x.upload.onprogress = (ev) => ev.lengthComputable && setProgress(Math.round((ev.loaded / ev.total) * 100))
        x.onload = () => {
          if (x.status >= 200 && x.status < 300) {
            try { resolve(JSON.parse(x.responseText)) } catch { resolve({}) }
          } else {
            let msg = `YouTube upload fail (${x.status})`
            try { msg = JSON.parse(x.responseText).error.message || msg } catch { /* keep default */ }
            reject(new Error(msg))
          }
        }
        x.onerror = () => reject(new Error('Upload beech mein ruk gaya — internet check karke dobara try karein.'))
        x.onabort = () => reject(new Error('Upload cancel kiya.'))
        x.send(file)
      })
      setDone({ id: video.id, privacy: video.status?.privacyStatus, uploadStatus: video.status?.uploadStatus })
      toast.success('Video YouTube par upload ho gaya')
      setFile(null)
      setF(EMPTY)
      setOpen(false)
      api.post(`/accounts/${accountId}/sync`).then(refreshAll).catch(() => {})
    } catch (err) {
      toast.error(err?.response ? errMsg(err) : err.message)
    } finally {
      setProgress(null)
      xhr.current = null
    }
  }

  return (
    <Panel
      title={<span className="flex items-center gap-2"><Upload className="size-4 text-primary" /> YouTube par video upload</span>}
      action={st.canUpload && <Button size="sm" variant={open ? 'ghost' : 'default'} onClick={() => setOpen((o) => !o)}>{open ? 'Band karein' : 'Naya video'}</Button>}
      className="mt-4"
    >
      {!st.canUpload ? (
        <p className="text-sm text-muted-foreground">
          {st.ownChannel ? 'Upload ke liye' : 'Upload sirf apne channel par hota hai —'} <Link href="/social-accounts" className="font-semibold text-primary underline">Social Accounts</Link> se is channel ko
          <b> Connect with Google</b> se {st.ownChannel ? 'ek baar dobara' : ''} jodein (upload permission Allow karein).
        </p>
      ) : !open ? (
        done ? (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <CheckCircle2 className="size-4 text-success" /> Upload ho gaya{done.privacy ? ` (${done.privacy})` : ''}.
            {done.id && <a className="text-primary underline" href={`https://www.youtube.com/watch?v=${done.id}`} target="_blank" rel="noreferrer">YouTube par dekhein</a>}
            <span className="text-xs text-muted-foreground">YouTube processing mein kuch minute lagte hain; list mein agle sync par aayega.</span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Video, title, description, tags aur schedule — seedha is channel par.</p>
        )
      ) : (
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit}>
          <Field label="Video file *" hint={file ? `${file.name} · ${mb(file.size)}` : 'MP4 / MOV / WebM'}>
            <Input type="file" accept="video/*" disabled={progress !== null} onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </Field>
          <Field label="Title * (max 100)">
            <Input required maxLength={100} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Diwali special offer 🎉" />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              <Textarea rows={4} maxLength={5000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
            </Field>
          </div>
          <Field label="Tags (comma se alag)">
            <Input value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} placeholder="diwali, offer, sweets" />
          </Field>
          <Field label="Visibility">
            <select className={selectClass} value={f.privacy} disabled={!!f.schedule} onChange={(e) => setF({ ...f, privacy: e.target.value })}>
              <option value="public">Public</option>
              <option value="unlisted">Unlisted (link wale hi dekh payenge)</option>
              <option value="private">Private</option>
            </select>
          </Field>
          <Field label="Schedule (optional)" hint="Diya to video tab tak private rahega, phir apne aap public">
            <Input type="datetime-local" value={f.schedule} onChange={(e) => setF({ ...f, schedule: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 pt-6 text-sm">
            <input type="checkbox" checked={f.madeForKids} onChange={(e) => setF({ ...f, madeForKids: e.target.checked })} />
            Ye video bachchon ke liye bana hai (Made for kids)
          </label>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            {progress === null ? (
              <Button type="submit"><Upload className="size-4" /> Upload karein</Button>
            ) : (
              <>
                <div className="h-2 w-60 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} /></div>
                <span className="text-sm font-semibold">{progress}%</span>
                <Button type="button" variant="ghost" size="sm" onClick={() => xhr.current?.abort()}>Cancel</Button>
              </>
            )}
          </div>
          <p className="text-xs text-muted-foreground sm:col-span-2">Upload ke dauran ye page band mat karein. File seedha aapke browser se YouTube par jaati hai.</p>
        </form>
      )}
    </Panel>
  )
}
