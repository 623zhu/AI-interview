import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'

interface User {
  id: string
  username: string
  email: string
  is_admin: boolean
  avatar_url?: string
}

const STORAGE_KEYS = {
  accessToken: 'access_token',
  refreshToken: 'refresh_token',
  user: 'auth_user',
}

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.user)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveUser(u: User | null) {
  if (u) {
    localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(u))
  } else {
    localStorage.removeItem(STORAGE_KEYS.user)
  }
}

export const useAuthStore = defineStore('auth', () => {
  // ---- State (restored from localStorage on init) ----
  const user = ref<User | null>(loadUser())
  const accessToken = ref<string>(localStorage.getItem(STORAGE_KEYS.accessToken) || '')
  const refreshTokenVal = ref<string>(localStorage.getItem(STORAGE_KEYS.refreshToken) || '')

  // ---- Computed ----
  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.is_admin ?? false)

  // ---- Cross-tab sync ----
  // When another tab changes localStorage (e.g. different user logs in),
  // sync this tab's in-memory auth state immediately.
  window.addEventListener('storage', (e) => {
    if (e.key === STORAGE_KEYS.accessToken) {
      accessToken.value = e.newValue || ''
    }
    if (e.key === STORAGE_KEYS.refreshToken) {
      refreshTokenVal.value = e.newValue || ''
    }
    if (e.key === STORAGE_KEYS.user) {
      user.value = e.newValue ? JSON.parse(e.newValue) : null
    }
  })

  // ---- Internal helpers ----
  function persistTokens(access: string, refresh: string) {
    accessToken.value = access
    refreshTokenVal.value = refresh
    localStorage.setItem(STORAGE_KEYS.accessToken, access)
    localStorage.setItem(STORAGE_KEYS.refreshToken, refresh)
  }

  function setAuth(data: { access_token: string; refresh_token: string; user?: User }) {
    persistTokens(data.access_token, data.refresh_token)
    if (data.user) {
      user.value = data.user
      saveUser(data.user)
    }
  }

  // ---- Actions ----
  async function login(email: string, password: string) {
    const res = await authApi.login({ email, password })
    const d = res.data.data
    setAuth({ access_token: d.tokens.access_token, refresh_token: d.tokens.refresh_token, user: d.user })
  }

  async function register(username: string, email: string, password: string, code: string) {
    await authApi.register({ username, email, password, code })
    // Backend returns user data but no tokens — user needs to login separately
  }

  async function refreshAccessToken() {
    const res = await authApi.refresh({ refresh_token: refreshTokenVal.value })
    const d = res.data.data
    persistTokens(d.access_token, d.refresh_token)
  }

  async function restoreSession() {
    if (!accessToken.value) return
    try {
      const res = await authApi.getMe()
      user.value = res.data.data
      saveUser(res.data.data)
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    accessToken.value = ''
    refreshTokenVal.value = ''
    localStorage.removeItem(STORAGE_KEYS.accessToken)
    localStorage.removeItem(STORAGE_KEYS.refreshToken)
    localStorage.removeItem(STORAGE_KEYS.user)
  }

  return {
    user, accessToken, refreshTokenVal, isLoggedIn, isAdmin,
    login, register, refreshAccessToken, restoreSession, logout,
    // Exposed for client.ts interceptor:
    persistTokens,
  }
})
