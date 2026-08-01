import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: attach token
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor: auto-refresh token on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // 登录/注册/刷新接口的 401 是业务错误（密码错误等），直接抛出，不刷新 token
    const url = originalRequest?.url || ''
    if (url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/refresh')) {
      return Promise.reject(error)
    }

    // 401 and not a retry → try refreshing
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('auth_user')
        window.location.href = '/login'
        return Promise.reject(error)
      }

      try {
        const res = await axios.post('/api/v1/auth/refresh', {
          refresh_token: refreshToken,
        })
        const data = res.data.data

        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)

        if (originalRequest.headers) {
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
        }
        return apiClient(originalRequest)
      } catch {
        localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('auth_user')
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
