import { useAuthStore } from '@/stores/auth'

let refreshPromise: Promise<void> | null = null

function withAccessToken(init: RequestInit, token: string): RequestInit {
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return { ...init, headers }
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const authStore = useAuthStore()
  let response = await fetch(input, withAccessToken(init, authStore.accessToken))
  if (response.status !== 401) return response
  await response.body?.cancel()

  if (!refreshPromise) {
    refreshPromise = authStore.refreshAccessToken().finally(() => {
      refreshPromise = null
    })
  }

  try {
    await refreshPromise
  } catch {
    authStore.logout()
    window.location.href = '/login'
    return response
  }

  response = await fetch(input, withAccessToken(init, authStore.accessToken))
  return response
}
