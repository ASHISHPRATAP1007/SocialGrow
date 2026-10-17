'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import { ArrowLeft, Copy, ExternalLink, MessageCircle, MessageSquare, Reply, Send, Share2, Sparkles, ThumbsUp } from 'lucide-react'
import { api } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { EmptyState, Loading, P_LABEL, Panel, PlatformBadge, Stat, can, errMsg, fmt, niceDate, selectClass, useMe } from '@/components/sg'
import { copyText } from '@/components/connect'

/** Any live post (YouTube / Facebook / Instagram): media, stats, all comments, replies, reply (or AI reply), share. */
export default function PostPage() {
  return (
    <Suspense fallback={<Loading />}>
      <PostView />
    </Suspense>
  )
}

function duration(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60
  return (h ? `${h}:${String(m).padStart(2, '0')}` : `${m}`) + `:${String(x).padStart(2, '0')}`
}

function ShareBar({ video }) {
  const url = video.url
  const title = (video.title || '').slice(0, 100)
  const text = `${title} — ${url}`
  const links = [
    ['WhatsApp', `https://wa.me/?text=${encodeURIComponent(text)}`, 'bg-[#25D366] text-white'],
    ['Facebook', `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`, 'bg-facebook text-white'],
    ['X', `https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}`, 'bg-foreground text-background'],
    ['LinkedIn', `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`, 'bg-[#0A66C2] text-white'],
  ]
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" onClick={async () => toast.success((await copyText(url)) ? 'Link copy ho gaya' : url)}>
        <Copy className="size-4" /> Copy link
      </Button>
      {links.map(([name, href, cls]) => (
        <a key={name} href={href} target="_blank" rel="noreferrer" className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium ${cls}`}>
          {name === 'WhatsApp' ? <MessageCircle className="size-4" /> : <Share2 className="size-4" />} {name}
        </a>
      ))}
      {typeof navigator !== 'undefined' && navigator.share && (
        <Button size="sm" variant="ghost" onClick={() => navigator.share({ title, url }).catch(() => {})}>
          <Share2 className="size-4" /> More
        </Button>
      )}
    </div>
  )
}

function ReplyBox({ postId, parentId, onDone, placeholder = 'Reply likhein…', autoFocus, aiFor }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [tone, setTone] = useState('friendly')
  const [ideas, setIdeas] = useState(null)
  const [thinking, setThinking] = useState(false)

  async function suggest() {
    setThinking(true)
    try {
      const { data } = await api.post(`/posts/${postId}/ai-reply`, { comment: aiFor.text, author: aiFor.author, tone })
      setIdeas(data.options)
      if (data.options[0] && !text) setText(data.options[0])
    } catch (err) {
      toast.error(errMsg(err))
    } finally {
      setThinking(false)
    }
  }

  return (
    <div className="mt-2">
      {aiFor && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" variant="outline" disabled={thinking} onClick={suggest}>
            <Sparkles className="size-4 text-primary" /> {thinking ? 'AI likh raha hai…' : ideas ? 'Aur options' : 'AI se reply likho'}
          </Button>
          <select className={selectClass + ' h-8 w-36 text-xs'} value={tone} onChange={(e) => setTone(e.target.value)} aria-label="Reply tone">
            <option value="friendly">Friendly</option>
            <option value="professional">Professional</option>
            <option value="funny">Thoda funny</option>
            <option value="short">Ekdum short</option>
          </select>
        </div>
      )}
      {ideas?.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {ideas.map((o, i) => (
            <button key={i} type="button" onClick={() => setText(o)}
              className={`rounded-full border px-3 py-1 text-left text-xs hover:border-primary ${text === o ? 'border-primary bg-primary/10' : ''}`}>{o}</button>
          ))}
        </div>
      )}
      <form
        className="flex items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault()
          if (!text.trim()) return
          setBusy(true)
          try {
            const { data } = await api.post(`/posts/${postId}/comments`, { text, parentId: parentId || null })
            setText('')
            setIdeas(null)
            toast.success(parentId ? 'Reply post ho gaya' : 'Comment post ho gaya')
            onDone(data)
          } catch (err) {
            toast.error(errMsg(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <Textarea rows={2} autoFocus={autoFocus} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className="min-h-0 flex-1" />
        <Button type="submit" size="sm" disabled={busy || !text.trim()}>
          <Send className="size-4" /> {busy ? 'Bhej rahe…' : 'Send'}
        </Button>
      </form>
    </div>
  )
}

function CommentItem({ c, small }) {
  return (
    <div className="flex gap-2">
      {c.authorImage ? <img src={c.authorImage} alt="" className={`${small ? 'size-6' : 'size-8'} shrink-0 rounded-full`} referrerPolicy="no-referrer" /> : <div className={`${small ? 'size-6' : 'size-8'} shrink-0 rounded-full bg-muted`} />}
      <div className="min-w-0">
        <div className="text-xs">
          <b>{c.author}</b> <span className="text-muted-foreground">· {c.publishedAt}</span>
        </div>
        <div className="mt-0.5 text-sm break-words whitespace-pre-line">{c.text}</div>
        <div className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground"><ThumbsUp className="size-3" /> {c.likes}</div>
      </div>
    </div>
  )
}

function Thread({ t, postId, canReply }) {
  const [replies, setReplies] = useState(t.replies)
  const [count, setCount] = useState(t.replyCount)
  const [open, setOpen] = useState(false)
  const [replying, setReplying] = useState(false)
  const [loading, setLoading] = useState(false)

  async function loadAll() {
    setLoading(true)
    try {
      const { data } = await api.get(`/posts/${postId}/comments/${t.id}/replies`)
      setReplies(data)
      setOpen(true)
    } catch (err) {
      toast.error(errMsg(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border-t py-3">
      <CommentItem c={t} />
      <div className="mt-1 flex flex-wrap gap-3 pl-10 text-xs">
        {canReply && (
          <button className="inline-flex items-center gap-1 font-semibold text-primary hover:underline" onClick={() => setReplying((r) => !r)}>
            <Reply className="size-3.5" /> Reply
          </button>
        )}
        {count > 0 && (
          <button className="font-semibold text-primary hover:underline" disabled={loading}
            onClick={() => (open ? setOpen(false) : replies.length >= count ? setOpen(true) : loadAll())}>
            {loading ? 'Loading…' : open ? 'Replies chhupayein' : `${count} ${count === 1 ? 'reply' : 'replies'} dekhein`}
          </button>
        )}
      </div>
      {replying && (
        <div className="pl-10">
          <ReplyBox postId={postId} parentId={t.id} autoFocus aiFor={t} placeholder={`@${t.author} ko reply…`}
            onDone={(r) => { setReplies((x) => [...x, r]); setCount((n) => n + 1); setOpen(true); setReplying(false) }} />
        </div>
      )}
      {open && replies.length > 0 && (
        <div className="mt-2 space-y-2 border-l-2 pl-4 ml-10">
          {replies.map((r) => <CommentItem key={r.id} c={r} small />)}
        </div>
      )}
    </div>
  )
}

function Comments({ postId, canReply, total, platform }) {
  const [order, setOrder] = useState('relevance')
  const [threads, setThreads] = useState(null)
  const [next, setNext] = useState(null)
  const [disabled, setDisabled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function load(pageToken) {
    setBusy(true)
    setErr(null)
    try {
      const { data } = await api.get(`/posts/${postId}/comments`, { params: { order, pageToken: pageToken || undefined } })
      setThreads((old) => (pageToken ? [...(old || []), ...data.items] : data.items))
      setNext(data.nextPageToken)
      setDisabled(!!data.disabled)
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    setThreads(null)
    void load(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postId, order])

  return (
    <Panel
      title={<span className="flex items-center gap-2"><MessageSquare className="size-4 text-primary" /> Comments ({fmt(total)})</span>}
      action={platform !== 'instagram' &&
        <div className="flex rounded-md border p-0.5 text-xs">
          {[['relevance', 'Top'], ['time', 'Newest']].map(([k, l]) => (
            <button key={k} onClick={() => setOrder(k)} className={`rounded px-2 py-1 font-semibold ${order === k ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>{l}</button>
          ))}
        </div>
      }
    >
      {canReply && <ReplyBox postId={postId} placeholder={platform === 'youtube' ? 'Channel ki taraf se naya comment likhein…' : 'Naya comment likhein…'} onDone={(c) => setThreads((x) => [c, ...(x || [])])} />}
      {err && <p className="mt-2 text-sm text-destructive">{err}</p>}
      {!threads ? (
        !err && <Loading label="Comments aa rahe hain…" />
      ) : disabled ? (
        <p className="mt-3 text-sm text-muted-foreground">Is video par comments band hain.</p>
      ) : threads.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">Abhi koi comment nahi.</p>
      ) : (
        <div className="mt-2">
          {threads.map((t) => <Thread key={t.id} t={t} postId={postId} canReply={canReply} />)}
          {next && (
            <Button variant="outline" size="sm" className="mt-3" disabled={busy} onClick={() => load(next)}>
              {busy ? 'Loading…' : 'Aur comments dikhayein'}
            </Button>
          )}
        </div>
      )}
    </Panel>
  )
}

function Media({ v }) {
  if (v.embedId) {
    return (
      <div className="overflow-hidden rounded-xl border bg-black shadow-sm">
        <div className="relative w-full" style={{ paddingTop: '56.25%' }}>
          <iframe className="absolute inset-0 size-full" src={`https://www.youtube-nocookie.com/embed/${v.embedId}?rel=0`} title={v.title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowFullScreen />
        </div>
      </div>
    )
  }
  if (!v.media?.length) {
    return (
      <div className="grid h-48 place-items-center rounded-xl border bg-muted/40 text-sm text-muted-foreground">
        {v.url ? <a href={v.url} target="_blank" rel="noreferrer" className="text-primary underline">{P_LABEL[v.platform]} par post dekhein</a> : 'Is post mein photo/video nahi hai'}
      </div>
    )
  }
  return (
    <div className={`grid gap-2 ${v.media.length > 1 ? 'grid-cols-2' : ''}`}>
      {v.media.slice(0, 10).map((m, i) => (
        <div key={i} className="overflow-hidden rounded-xl border bg-black">
          {m.type === 'video'
            ? <video src={m.url} poster={m.thumbnail || undefined} controls playsInline className="max-h-[70vh] w-full" />
            : <img src={m.url} alt="" className="max-h-[70vh] w-full object-contain" referrerPolicy="no-referrer" />}
        </div>
      ))}
    </div>
  )
}

function PostView() {
  const id = useSearchParams().get('id')
  const me = useMe()
  const { data: v, error } = useApi(id ? `/posts/${id}/detail` : null)
  const [more, setMore] = useState(false)

  if (!id) return <EmptyState title="Post chunein" text="Account details ya Posts page se kisi post par click karein." />
  if (error) return <EmptyState title="Post nahi khul payi" text={errMsg(error)} />
  if (!v) return <Loading />

  const canReply = v.canReply && can(me.role, 'content')
  const desc = v.text || ''
  const yt = v.platform === 'youtube'

  return (
    <>
      <Link href={`/account?id=${v.accountId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary">
        <ArrowLeft className="size-4" /> @{v.username}
      </Link>
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <Media v={v} />
          <div>
            <h1 className="flex items-start gap-2 text-xl font-bold"><PlatformBadge platform={v.platform} label={false} /> {yt ? v.title : (v.title || 'Post')}</h1>
            <div className="mt-1 text-sm text-muted-foreground">
              {v.channelTitle || `@${v.username}`} · {v.publishedAt ? niceDate(v.publishedAt) : ''}{v.durationSeconds ? ` · ${duration(v.durationSeconds)}` : ''} · {v.format}
            </div>
          </div>
          <div className={`grid gap-3 ${yt ? 'grid-cols-3' : v.platform === 'facebook' ? 'grid-cols-3' : 'grid-cols-2'}`}>
            {yt && <Stat label="Views" value={fmt(v.views)} />}
            <Stat label={v.platform === 'facebook' ? 'Reactions' : 'Likes'} value={fmt(v.likes)} hint={yt && v.views ? `${((v.likes / v.views) * 100).toFixed(2)}% of views` : undefined} />
            <Stat label="Comments" value={fmt(v.comments)} />
            {v.platform === 'facebook' && <Stat label="Shares" value={fmt(v.shares)} />}
          </div>
          {v.url && (
            <Panel title="Share karein">
              <ShareBar video={{ ...v, title: v.title || desc }} />
              <a href={v.url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">
                {P_LABEL[v.platform]} par kholein <ExternalLink className="size-3" />
              </a>
            </Panel>
          )}
          {desc && (
            <Panel title={yt ? 'Description' : 'Caption'}>
              <p className="text-sm whitespace-pre-line">{more || desc.length <= 400 ? desc : desc.slice(0, 400) + '…'}</p>
              {desc.length > 400 && <button className="mt-1 text-xs font-semibold text-primary" onClick={() => setMore((m) => !m)}>{more ? 'Kam' : 'Aur padhein'}</button>}
            </Panel>
          )}
        </div>
        <div>
          {!v.canReply && v.replyHint && <p className="mb-3 rounded-md bg-warning-soft p-3 text-xs">{v.replyHint}</p>}
          <Comments postId={v.postId} canReply={canReply} total={v.comments} platform={v.platform} />
        </div>
      </div>
    </>
  )
}
