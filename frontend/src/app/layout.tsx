import type { Metadata } from 'next'
import { Fraunces, Geist, Geist_Mono } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/Providers'
import { Navbar } from '@/components/Navbar'

const fraunces = Fraunces({ subsets: ['latin'], axes: ['opsz', 'SOFT'], variable: '--font-fraunces', display: 'swap' })
const geist = Geist({ subsets: ['latin'], variable: '--font-geist', display: 'swap' })
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono', display: 'swap' })

export const metadata: Metadata = {
  title: 'AURA3',
  description: 'Evidence-first startup investing: TitanOCR deck evidence, AI due diligence and AuraCoin DAO rounds.',
  icons: {
    icon: '/icon.png',
    shortcut: '/icon.png',
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${geist.variable} ${geistMono.variable}`}>
      <body className="min-h-screen bg-paper-2 font-sans text-[16px] text-slate-900 selection:bg-jade-100">
        <Providers>
          <div className="relative flex min-h-screen flex-col">
            <Navbar />
            <main className="relative w-full flex-1">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  )
}
