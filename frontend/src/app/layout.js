import { Toaster } from 'sonner'
import './globals.css'

export const metadata = {
  title: 'SocialGrow AI — Social analytics & AI for agencies',
  description:
    'Connect Instagram, Facebook and YouTube, track real growth, get AI insights, plan content and send white-label client reports.',
  icons: { icon: '/favicon.svg' },
}

export const viewport = { width: 'device-width', initialScale: 1 }

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        {children}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  )
}
