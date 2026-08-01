<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { questionApi } from '@/api/questions'
import { jobApi } from '@/api/jobs'
import type { QuestionCreate, QuestionUpdate } from '@/types/question'
import type { SkillTree } from '@/types/job'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => route.name === 'QuestionEdit')
const pageTitle = computed(() => isEdit.value ? '编辑题目' : '新增题目')
const loading = ref(false)
const saving = ref(false)

const form = ref<QuestionCreate>({
  category: 'concept', difficulty: 'medium',
  content: '', expected_points: '', reference_answer: '',
  skill_nodes: [], evaluation_criteria: null,
})

const categoryOptions = [
  { label: '概念理解', value: 'concept' },
  { label: '原理理解', value: 'principle' },
  { label: '工程实践', value: 'practice' },
  { label: '优化能力', value: 'optimization' },
  { label: '系统设计', value: 'design' },
]
const difficultyOptions = ['easy', 'medium', 'hard']

// ── Skill tree picker ──────────────────────────────────

interface SkillOption {
  value: string       // path: "数据库/事务与锁" or "数据库/事务与锁/隔离级别"
  label: string       // display name
  children?: SkillOption[]
}

const skillTreeOptions = ref<SkillOption[]>([])
const selectedSkills = ref<string[]>([])

function flattenTree(tree: SkillTree | null): SkillOption[] {
  if (!tree?.domains) return []
  return tree.domains.map(d => ({
    value: d.name,
    label: d.name,
    children: (d.skills || []).map(s => ({
      value: `${d.name}/${s.name}`,
      label: `${s.name} (${s.level || 'medium'})`,
      children: (s.children || []).map(c => ({
        value: `${d.name}/${s.name}/${c.name}`,
        label: c.name,
      })),
    })),
  }))
}

async function loadSkillTree() {
  try {
    const res = await jobApi.list({ include_inactive: false, page_size: 100 })
    const jobs = res.data.data.items
    // Merge skill trees from all active jobs
    const seen = new Set<string>()
    const merged: SkillOption[] = []
    for (const job of jobs) {
      try {
        const detail = (await jobApi.get(job.id)).data.data
        const options = flattenTree(detail.skill_tree)
        for (const opt of options) {
          if (!seen.has(opt.value)) {
            seen.add(opt.value)
            merged.push(opt)
          }
        }
      } catch { /* skip */ }
    }
    skillTreeOptions.value = merged
  } catch { /* no jobs yet */ }
}

// ── Load / Save ────────────────────────────────────────

async function loadQuestion() {
  if (!isEdit.value) return
  loading.value = true
  try {
    const res = await questionApi.get(route.params.id as string)
    const d = res.data.data
    form.value = {
      category: d.category, difficulty: d.difficulty,
      content: d.content, expected_points: d.expected_points ?? '',
      reference_answer: d.reference_answer ?? '',
      skill_nodes: d.skill_nodes ?? [],
      evaluation_criteria: d.evaluation_criteria ?? null,
    }
    selectedSkills.value = d.skill_nodes || []
  } catch {
    ElMessage.error('加载题目失败'); router.push('/admin/questions')
  } finally { loading.value = false }
}

async function handleSave() {
  if (!form.value.content.trim()) { ElMessage.warning('请输入题目内容'); return }
  if (!form.value.expected_points?.trim()) { ElMessage.warning('请输入核心考察点'); return }
  if (!form.value.reference_answer?.trim()) { ElMessage.warning('请输入参考答案'); return }

  form.value.skill_nodes = selectedSkills.value.filter(s => s)

  saving.value = true
  try {
    if (isEdit.value) {
      await questionApi.update(route.params.id as string, { ...form.value } as QuestionUpdate)
      ElMessage.success('保存成功')
    } else {
      await questionApi.create(form.value)
      ElMessage.success('创建成功'); router.push('/admin/questions')
    }
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

function goBack() { router.push('/admin/questions') }

onMounted(() => { loadSkillTree(); loadQuestion() })
</script>

<template>
  <div class="question-edit">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="goBack">返回列表</el-button>
      <h2>{{ pageTitle }}</h2><div></div>
    </div>

    <el-card v-loading="loading">
      <el-form :model="form" label-width="100px" style="max-width: 900px">

        <el-form-item label="题目内容" required>
          <el-input v-model="form.content" type="textarea" :rows="3" placeholder="请输入面试题目..." />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="分类">
              <el-select v-model="form.category" style="width:100%">
                <el-option v-for="o in categoryOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" style="width:100%">
                <el-option v-for="v in difficultyOptions" :key="v" :label="v" :value="v" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="关联技能">
          <el-tree-select
            v-model="selectedSkills"
            :data="skillTreeOptions"
            multiple
            show-checkbox
            check-strictly
            clearable
            placeholder="选择此题考察的技能点（可多选）"
            style="width:100%"
            :props="{ label: 'label', children: 'children' }"
          />
          <span class="form-hint">从岗位技能树中选择，用于面试覆盖度跟踪和候选人画像</span>
        </el-form-item>

        <el-form-item label="核心考察点" required>
          <el-input v-model="form.expected_points" type="textarea" :rows="4"
            placeholder="描述核心考察点和评分维度，供 AI 评分参考。例如：考察对事务ACID的理解，需能说出四个特性的含义并能举例说明。" />
          <span class="form-hint">AI 会根据此处描述的维度和要点对候选人回答进行评分</span>
        </el-form-item>

        <el-form-item label="参考答案" required>
          <el-input v-model="form.reference_answer" type="textarea" :rows="10"
            placeholder="提供一份参考答案，供 AI 评估时对比。写出关键思路和核心知识点即可" />
          <span class="form-hint">供 AI 对比参考，不是标准答案。写出核心思路和关键点即可</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ isEdit ? '保存修改' : '创建题目' }}
          </el-button>
          <el-button @click="goBack">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.question-edit { padding: 0 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; flex: 1; text-align: center; }
.form-hint { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
