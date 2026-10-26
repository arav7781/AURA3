import { NextResponse, type NextRequest } from 'next/server'
import { decodeJwt } from 'jose'

// Optimistic route guard. It only reads the session cookie's claims to route people: signed-out
// visitors go to /login, and each role lands on its own dashboard. The API verifies the JWT's
// signature and session on every request, so nothing here is trusted for access to data.

const SESSION_COOKIE = 'aura_session'
const HOME = { investor: '/investor', startup: '/founder' } as const

function sessionRole(request: NextRequest): keyof typeof HOME | null {
  const token = request.cookies.get(SESSION_COOKIE)?.value
  if (!token) return null
  try {
    const claims = decodeJwt(token)
    if (typeof claims.exp === 'number' && claims.exp * 1000 < Date.now()) return null
    return claims.role === 'investor' || claims.role === 'startup' ? claims.role : null
  } catch {
    return null
  }
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const role = sessionRole(request)
  if (!role) {
    const login = new URL('/login', request.url)
    login.searchParams.set('next', pathname + search)
    return NextResponse.redirect(login)
  }
  if (pathname.startsWith('/investor') && role !== 'investor') return NextResponse.redirect(new URL(HOME[role], request.url))
  if (pathname.startsWith('/founder') && role !== 'startup') return NextResponse.redirect(new URL(HOME[role], request.url))
  return NextResponse.next()
}

export const config = {
  // Never /api (uploads would be cut at the proxy body limit) or static assets.
  matcher: [
    '/investor/:path*',
    '/founder/:path*',
    '/portfolio/:path*',
    '/evaluation/:path*',
    '/evaluations/:path*',
    '/proposal/:path*',
    '/startup/:path*',
    '/finscope/:path*',
    '/exit-window/:path*',
  ],
}
