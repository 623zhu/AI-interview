import apiClient from './client'

export interface AdminDashboardData {
  summary: {
    total_users: number
    total_questions: number
    total_interviews: number
    completed_interviews: number
    completion_rate: number
  }
  interview_trend: { date: string; count: number }[]
  user_trend: { date: string; count: number }[]
  job_popularity: { title: string; category: string; count: number }[]
  category_distribution: { category: string; count: number }[]
  recent_interviews: {
    id: string
    username: string
    job_title: string
    status: string
    created_at: string | null
  }[]
}

export interface AdminUserItem {
  id: string
  username: string
  email: string
  is_admin: boolean
  is_active: boolean
  avatar_url: string | null
  interview_count: number
  avg_score: number | null
  last_activity: string | null
  created_at: string | null
}

export interface AdminUserList {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminUserDetail {
  id: string
  username: string
  email: string
  is_admin: boolean
  is_active: boolean
  avatar_url: string | null
  created_at: string | null
  stats: {
    interview_count: number
    avg_score: number | null
  }
  recent_interviews: {
    id: string
    status: string
    job_title: string | null
    total_questions: number
    current_question: number
    score: number | null
    duration_seconds: number | null
    created_at: string | null
  }[]
}

export const adminApi = {
  getDashboard() {
    return apiClient.get<{ code: number; data: AdminDashboardData }>('/admin/dashboard')
  },

  getUsers(params?: { page?: number; page_size?: number; keyword?: string }) {
    return apiClient.get<{ code: number; data: AdminUserList }>('/admin/users', { params })
  },

  getUserDetail(userId: string) {
    return apiClient.get<{ code: number; data: AdminUserDetail }>(`/admin/users/${userId}`)
  },

  updateUser(userId: string, data: { is_active?: boolean }) {
    return apiClient.patch<{ code: number; message: string; data: any }>(
      `/admin/users/${userId}`,
      null,
      { params: data }
    )
  },
}
