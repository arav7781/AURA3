'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { getDashboardPath, useAuth, type UserRole } from '@/context/AuthContext'

/** Renders its children only for a signed-in user (of ``role``, when given); otherwise redirects. */
export function RequireRole({ role, children }: { role?: UserRole; children: React.ReactNode }) {
  const { me, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const allowed = !!me && (!role || me.user.role === role)

  useEffect(() => {
    if (loading || allowed) return
    router.replace(me ? getDashboardPath(me.user.role) : `/login?next=${encodeURIComponent(pathname)}`)
  }, [loading, allowed, me, pathname, router])

  if (!allowed) {
    return (
      <div className="flex justify-center py-24 text-slate-400" aria-busy="true">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    )
  }
  return <>{children}</>
}
