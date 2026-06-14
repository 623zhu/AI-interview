/** Question types for admin CRUD */

export interface QuestionListItem {
  id: string
  category: string
  difficulty: string
  skill_nodes: string[] | null
  content: string
  expected_points: string | null
  source: string
  usage_count: number
  avg_score: number | null
  is_active: boolean
}

export interface QuestionDetail extends QuestionListItem {
  reference_answer: string | null
  evaluation_criteria: Record<string, unknown> | null
  created_at: string
}

export interface QuestionCreate {
  content: string
  expected_points: string
  reference_answer: string | null
  category?: string
  difficulty?: string
  skill_nodes?: string[] | null
  evaluation_criteria?: Record<string, unknown> | null
}

export interface QuestionUpdate {
  category?: string | null
  difficulty?: string | null
  skill_nodes?: string[] | null
  content?: string | null
  expected_points?: string | null
  reference_answer?: string | null
  evaluation_criteria?: Record<string, unknown> | null
  is_active?: boolean | null
}

export interface QuestionImportItem {
  content: string
  expected_points: string
  reference_answer: string
  category?: string
  difficulty?: string
  skill_nodes?: string[] | null
  evaluation_criteria?: Record<string, unknown> | null
}

export interface QuestionImportResult {
  total: number
  success: number
  failed: number
  errors: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
