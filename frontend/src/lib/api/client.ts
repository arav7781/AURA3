// Calls the AURA-3 API through this origin (next.config.ts forwards /api/* to FastAPI), so the
// HttpOnly session cookie (a signed JWT) is first-party and never readable by page scripts.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  idempotencyKey?: string
  signal?: AbortSignal
}

export async function api<T>(path: string, { method = 'GET', body, idempotencyKey, signal }: RequestOptions = {}): Promise<T> {
  // The custom header is the CSRF guard: a cross-site form cannot send it.
  const headers: Record<string, string> = { 'X-Aura-CSRF': '1' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the AURA-3 API. Is the backend running?')
  }

  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = data?.error
    throw new ApiError(
      response.status,
      error?.code ?? `HTTP_${response.status}`,
      error?.message ?? (response.status >= 500 ? 'The server had a problem. Try again.' : response.statusText),
      error?.details ?? {},
    )
  }
  return data as T
}

/** The first field-level message of a 422, or the error's own message. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const errors = error.details?.errors as { loc: string[]; msg: string }[] | undefined
    if (error.code === 'VALIDATION_ERROR' && errors?.length) {
      const { loc, msg } = errors[0]
      const field = loc[loc.length - 1]
      return `${field.replace(/_/g, ' ')}: ${msg.replace(/^Value error, /, '')}`
    }
    return error.message
  }
  return error instanceof Error ? error.message : 'Something went wrong'
}
