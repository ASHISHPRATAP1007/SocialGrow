'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Search } from 'lucide-react'

/**
 * Searchable client dropdown — works for 3 clients or 3,000.
 * value '' = nothing / "all" (when allowAll). Type to filter, ↑↓ to move, Enter to pick, Esc to close.
 */
export function ClientPicker({ clients, value, onChange, allowAll = false, allLabel = 'Sab clients', placeholder = 'Client chunein', className = '', disabled }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [hi, setHi] = useState(0)
  const box = useRef(null)
  const input = useRef(null)

  const list = clients || []
  const selected = list.find((c) => c.id === value)
  const needle = q.trim().toLowerCase()
  const matches = list.filter((c) => !needle || `${c.name} ${c.company || ''}`.toLowerCase().includes(needle))
  const options = [...(allowAll && !needle ? [{ id: '', name: allLabel }] : []), ...matches]

  useEffect(() => {
    if (!open) return
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    setTimeout(() => input.current?.focus(), 0)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  function pick(id) {
    onChange(id)
    setOpen(false)
    setQ('')
  }

  return (
    <div ref={box} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => { setOpen((o) => !o); setHi(0) }}
        className="flex h-9 w-full min-w-44 items-center justify-between gap-2 rounded-md border bg-background px-3 text-left text-sm shadow-xs hover:bg-muted/50 disabled:opacity-50"
      >
        <span className={`truncate ${selected || (allowAll && !value) ? '' : 'text-muted-foreground'}`}>
          {selected ? selected.name : allowAll ? allLabel : placeholder}
        </span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full min-w-60 rounded-md border bg-card text-card-foreground shadow-lg">
          <div className="flex items-center gap-2 border-b px-2">
            <Search className="size-4 text-muted-foreground" />
            <input
              ref={input}
              value={q}
              onChange={(e) => { setQ(e.target.value); setHi(0) }}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') { e.preventDefault(); setHi((h) => Math.min(h + 1, options.length - 1)) }
                else if (e.key === 'ArrowUp') { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)) }
                else if (e.key === 'Enter') { e.preventDefault(); if (options[hi]) pick(options[hi].id) }
                else if (e.key === 'Escape') setOpen(false)
              }}
              placeholder="Client ka naam search karein…"
              aria-label="Search clients"
              className="h-9 w-full bg-transparent text-sm outline-none"
            />
          </div>
          <ul role="listbox" className="max-h-64 overflow-y-auto py-1">
            {options.length === 0 && <li className="px-3 py-2 text-sm text-muted-foreground">Koi client nahi mila</li>}
            {options.map((c, i) => (
              <li
                key={c.id || '__all'}
                role="option"
                aria-selected={c.id === value}
                onMouseEnter={() => setHi(i)}
                onMouseDown={(e) => { e.preventDefault(); pick(c.id) }}
                className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-1.5 text-sm ${i === hi ? 'bg-muted' : ''}`}
              >
                <span className="min-w-0">
                  <span className="block truncate">{c.name}</span>
                  {c.company && <span className="block truncate text-[11px] text-muted-foreground">{c.company}</span>}
                </span>
                {c.id === value && <Check className="size-4 shrink-0 text-primary" />}
              </li>
            ))}
          </ul>
          {list.length > 0 && <div className="border-t px-3 py-1 text-[11px] text-muted-foreground">{matches.length} / {list.length} clients</div>}
        </div>
      )}
    </div>
  )
}
