import apiClient from './client'

export const authApi = {
  sendCode(email: string) {
    return apiClient.post('/auth/send-code', { email })
  },

  register(data: { username: string; email: string; password: string; code: string }) {
    return apiClient.post('/auth/register', data)
  },

  login(data: { email: string; password: string }) {
    return apiClient.post('/auth/login', data)
  },

  refresh(data: { refresh_token: string }) {
    return apiClient.post('/auth/refresh', data)
  },

  logout() {
    return apiClient.post('/auth/logout')
  },

  getMe() {
    return apiClient.get('/auth/me')
  },
}
