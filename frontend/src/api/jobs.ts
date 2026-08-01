import apiClient from './client'
import type {
  JobListItem,
  JobDetail,
  JobCreate,
  JobUpdate,
} from '@/types/job'
import type { PaginatedResponse } from '@/types/question'

export const jobApi = {
  /** List jobs (supports include_inactive for admin) */
  list(params: {
    page?: number
    page_size?: number
    category?: string
    level?: string
    keyword?: string
    include_inactive?: boolean
  } = {}) {
    return apiClient.get<{ code: number; data: PaginatedResponse<JobListItem> }>(
      '/jobs', { params }
    )
  },

  /** Get job detail */
  get(id: string) {
    return apiClient.get<{ code: number; data: JobDetail }>(`/jobs/${id}`)
  },

  /** [Admin] Create job */
  create(data: JobCreate) {
    return apiClient.post<{ code: number; data: JobDetail }>('/jobs', data)
  },

  /** [Admin] Update job */
  update(id: string, data: JobUpdate) {
    return apiClient.put<{ code: number; data: JobDetail }>(`/jobs/${id}`, data)
  },

  /** [Admin] Delete job */
  delete(id: string) {
    return apiClient.delete<{ code: number; message: string }>(`/jobs/${id}`)
  },

  /** [Admin] Toggle active/inactive */
  toggle(id: string) {
    return apiClient.post<{ code: number; data: { id: string; is_active: boolean }; message: string }>(
      `/jobs/${id}/toggle`
    )
  },

}
