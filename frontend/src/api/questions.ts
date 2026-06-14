import apiClient from './client'
import type {
  QuestionListItem,
  QuestionDetail,
  QuestionCreate,
  QuestionUpdate,
  QuestionImportItem,
  QuestionImportResult,
  PaginatedResponse,
} from '@/types/question'

export const questionApi = {
  /** List questions (supports include_inactive for admin) */
  list(params: {
    page?: number
    page_size?: number
    category?: string
    difficulty?: string
    job_category?: string
    keyword?: string
    include_inactive?: boolean
  } = {}) {
    return apiClient.get<{ code: number; data: PaginatedResponse<QuestionListItem> }>(
      '/questions', { params }
    )
  },

  /** Get question detail */
  get(id: string) {
    return apiClient.get<{ code: number; data: QuestionDetail }>(`/questions/${id}`)
  },

  /** [Admin] Create question */
  create(data: QuestionCreate) {
    return apiClient.post<{ code: number; data: QuestionDetail }>('/questions', data)
  },

  /** [Admin] Update question */
  update(id: string, data: QuestionUpdate) {
    return apiClient.put<{ code: number; data: QuestionDetail }>(`/questions/${id}`, data)
  },

  /** [Admin] Delete question */
  delete(id: string) {
    return apiClient.delete<{ code: number; message: string }>(`/questions/${id}`)
  },

  /** [Admin] Batch delete */
  batchDelete(ids: string[]) {
    return apiClient.post<{ code: number; message: string }>('/questions/batch-delete', ids)
  },

  /** [Admin] Toggle active/inactive */
  toggle(id: string) {
    return apiClient.post<{ code: number; data: { id: string; is_active: boolean }; message: string }>(
      `/questions/${id}/toggle`
    )
  },

  /** [Admin] Batch import */
  importItems(items: QuestionImportItem[]) {
    return apiClient.post<{ code: number; data: QuestionImportResult }>('/questions/import', items)
  },

  /** [Admin] Sync to Chroma */
  sync() {
    return apiClient.post<{ code: number; message: string }>('/questions/sync')
  },
}
