import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/Providers'
import { Navbar } from '@/components/Navbar'
import { CustomCursor } from '@/components/CustomCursor'
import { NewsTicker } from '@/components/NewsTicker'
import { AuthProvider } from '@/context/AuthContext'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'AURA3 Platform',
  description: 'Decentralized Capital Intelligence Protocol',
  icons: {
    icon: '/icon.png',
    shortcut: '/icon.png',
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen bg-white text-black text-[17px] md:text-[18px] selection:bg-gray-300`}>
        <CustomCursor />
        <AuthProvider>
          <Providers>
            <div className="relative flex flex-col min-h-screen">
              {/* Live Data Mesh - Moving Flow */}
              <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
                 {/* Grid texture that slow-scrolls upwards */}
                 <div className="absolute inset-0 bg-[linear-gradient(rgba(3,225,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(3,225,255,0.03)_1px,transparent_1px)] bg-[size:50px_50px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_0%,#000_10%,transparent_100%)] opacity-60 animate-[pulse_8s_ease-in-out_infinite]" />
                 
                 {/* Ambient Blobs */}
                 <div className="absolute -top-1/4 -right-1/4 w-[800px] h-[800px] bg-[#03e1ff]/[0.05] blur-[150px] rounded-full animate-[spin_12s_linear_infinite]" />
                 <div className="absolute bottom-0 -left-1/4 w-[600px] h-[600px] bg-[#00ffbd]/[0.03] blur-[150px] rounded-full animate-[pulse_10s_ease-in-out_infinite]" />
              </div>
              
              <Navbar />
              <NewsTicker />
              <main className="flex-1 relative z-10 w-full">
                {children}
              </main>
            </div>
          </Providers>
        </AuthProvider>
      </body>
    </html>
  )
}
