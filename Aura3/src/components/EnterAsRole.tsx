'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth, UserRole, getDashboardPath } from '@/context/AuthContext'

// Old /auth/* links land here: enter the demo role and go straight to its dashboard.
export function EnterAsRole({ role }: { role: UserRole }) {
  const router = useRouter()
  const { enterAs } = useAuth()

  useEffect(() => {
    enterAs(role)
    router.replace(getDashboardPath(role))
  }, [enterAs, role, router])

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="w-8 h-8 rounded-full border-2 border-[#0284c7] border-t-transparent animate-spin" />
    </div>
  )
}
