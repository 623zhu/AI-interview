/** Job position types for admin CRUD */

export interface JobListItem {
  id: string
  title: string
  category: string
  level: string
  salary_range: string | null
  company_type: string
  is_active: boolean
}

export interface SkillNode {
  name: string
  level?: 'easy' | 'medium' | 'hard'
  children?: SkillNode[]
}

export interface SkillTree {
  domains: {
    name: string
    weight: number
    skills: SkillNode[]
  }[]
}

export interface JobDetail extends JobListItem {
  description: string | null
  requirements: Record<string, unknown>
  skill_tree: SkillTree | null
  created_at: string
}

export interface JobCreate {
  title: string
  category: string
  level?: string
  description?: string | null
  requirements: Record<string, unknown>
  skill_tree?: SkillTree | null
  salary_range?: string | null
  company_type?: string
  is_active?: boolean
}

export interface JobUpdate {
  title?: string | null
  category?: string | null
  level?: string | null
  description?: string | null
  requirements?: Record<string, unknown> | null
  skill_tree?: SkillTree | null
  salary_range?: string | null
  company_type?: string | null
  is_active?: boolean | null
}
