import type { Metadata } from 'next'
import { Archivo, Hanken_Grotesk, Martian_Mono } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/Providers'
import { Navbar } from '@/components/Navbar'

const archivo = Archivo({ subsets: ['latin'], axes: ['wdth'], variable: '--font-archivo', display: 'swap' })
const hanken = Hanken_Grotesk({ subsets: ['latin'], variable: '--font-hanken', display: 'swap' })
const martian = Martian_Mono({ subsets: ['latin'], axes: ['wdth'], variable: '--font-martian', display: 'swap' })

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
    <html lang="en" className={`${archivo.variable} ${hanken.variable} ${martian.variable}`}>
      <body className="min-h-screen bg-white font-sans text-[16px] text-slate-900 selection:bg-sky-100">
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
