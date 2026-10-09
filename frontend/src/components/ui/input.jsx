import { cn } from '@/lib/utils'

const field =
  'w-full min-w-0 rounded-md border border-input bg-card px-3 text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50'

export function Input({ className, ...props }) {
  return <input className={cn(field, 'h-9 py-1', className)} {...props} />
}

export function Textarea({ className, ...props }) {
  return <textarea className={cn(field, 'min-h-16 py-2', className)} {...props} />
}
