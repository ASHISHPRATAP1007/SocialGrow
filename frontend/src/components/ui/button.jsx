import Link from 'next/link'
import { cn } from '@/lib/utils'

const base =
  'inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0'

const variants = {
  default: 'bg-primary text-primary-foreground shadow-xs hover:bg-primary/90',
  outline: 'border bg-card shadow-xs hover:bg-muted',
  ghost: 'hover:bg-muted',
  destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
}

const sizes = {
  default: 'h-9 px-4 py-2',
  sm: 'h-8 gap-1.5 rounded-md px-3',
  icon: 'size-9',
}

export function buttonClass({ variant = 'default', size = 'default', className } = {}) {
  return cn(base, variants[variant], sizes[size], className)
}

export function Button({ variant, size, className, type = 'button', ...props }) {
  return <button type={type} className={buttonClass({ variant, size, className })} {...props} />
}

/** A Next.js link that looks like a button. */
export function ButtonLink({ variant, size, className, ...props }) {
  return <Link className={buttonClass({ variant, size, className })} {...props} />
}
