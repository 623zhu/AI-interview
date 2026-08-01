<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Delete } from '@element-plus/icons-vue'
import { jobApi } from '@/api/jobs'
import type { JobCreate, JobUpdate, SkillTree, SkillNode } from '@/types/job'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => route.name === 'JobEdit')
const pageTitle = computed(() => isEdit.value ? '编辑岗位' : '新增岗位')
const loading = ref(false)
const saving = ref(false)

const form = ref<JobCreate>({
  title: '', category: 'backend', level: 'mid', description: '',
  requirements: { skills: [] }, skill_tree: null,
})

const skillsText = ref('')

// ── Skill Tree ─────────────────────────────────────────

interface Domain {
  name: string
  weight: number   // raw relative weight, will be normalized
  skills: SkillNode[]
}

const domains = ref<Domain[]>([])

const categoryOptions = [
  { label: '前端', value: 'frontend' }, { label: '后端', value: 'backend' },
  { label: '全栈', value: 'fullstack' }, { label: '数据', value: 'data' },
  { label: 'AI应用', value: 'ai' }, { label: '运维', value: 'devops' },
  { label: '测试', value: 'qa' },
]
const levelOptions = ['junior', 'mid', 'senior', 'lead']
const diffOptions = ['easy', 'medium', 'hard']

// ── normalized weight display ──────────────────────────

const weightPct = computed(() => {
  const result: Record<number, number> = {}
  const total = domains.value.reduce((s, d) => s + (d.weight || 0), 0)
  domains.value.forEach((d, i) => {
    result[i] = total > 0 ? Math.round((d.weight / total) * 100) : 0
  })
  return result
})

// ── mutations ──────────────────────────────────────────

function addDomain()   { domains.value.push({ name: '', weight: 10, skills: [] }) }
function removeDomain(i: number) { domains.value.splice(i, 1) }
function addSkill(di: number)    { domains.value[di].skills.push({ name: '' }) }
function removeSkill(di: number, si: number) { domains.value[di].skills.splice(si, 1) }
function addChild(di: number, si: number) {
  const skill = domains.value[di].skills[si]
  if (!skill.children) skill.children = []
  skill.children.push({ name: '' })
}
function removeChild(di: number, si: number, ci: number) {
  domains.value[di].skills[si].children?.splice(ci, 1)
}

// ── Tree ↔ JSON ────────────────────────────────────────

function serializeSkills(skills: SkillNode[]): SkillNode[] {
  return skills
    .filter(s => s.name.trim())
    .map(s => ({
      name: s.name.trim(),
      level: s.level || 'medium',
      children: s.children ? serializeSkills(s.children) : undefined,
    }))
}

function treeToJson(): SkillTree | null {
  const filtered = domains.value.filter(d => d.name.trim())
  if (filtered.length === 0) return null
  const total = filtered.reduce((s, d) => s + (d.weight || 0), 0)
  return {
    domains: filtered.map(d => ({
      name: d.name.trim(),
      weight: total > 0 ? +(d.weight / total).toFixed(2) : +(1 / filtered.length).toFixed(2),
      skills: serializeSkills(d.skills),
    })),
  }
}

function deserializeSkills(skills: SkillNode[]): SkillNode[] {
  return (skills || []).map(s => ({
    name: s.name,
    level: s.level || 'medium',
    children: s.children ? deserializeSkills(s.children) : undefined,
  }))
}

function jsonToTree(st: SkillTree | null) {
  domains.value = []
  if (!st?.domains) return
  domains.value = st.domains.map(d => ({
    name: d.name,
    weight: Math.round(d.weight * 100),  // store as integer for editing
    skills: deserializeSkills(d.skills || []),
  }))
}

// ── Load / Save ────────────────────────────────────────

async function loadJob() {
  if (!isEdit.value) return
  loading.value = true
  try {
    const res = await jobApi.get(route.params.id as string)
    const d = res.data.data
    form.value = {
      title: d.title, category: d.category, level: d.level,
      description: d.description || '',
      requirements: d.requirements || { skills: [] },
      skill_tree: d.skill_tree,
    }
    if (d.requirements && Array.isArray(d.requirements.skills)) {
      skillsText.value = d.requirements.skills.join(', ')
    }
    jsonToTree(d.skill_tree)
  } catch { ElMessage.error('加载岗位失败'); router.push('/admin/jobs')
  } finally { loading.value = false }
}

async function handleSave() {
  if (!form.value.title.trim()) { ElMessage.warning('请输入岗位名称'); return }
  form.value.skill_tree = treeToJson()
  form.value.requirements = {
    skills: skillsText.value.split(/[,，]/).map(s => s.trim()).filter(s => s.length > 0),
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await jobApi.update(route.params.id as string, { ...form.value } as JobUpdate)
      ElMessage.success('保存成功')
    } else {
      await jobApi.create(form.value)
      ElMessage.success('创建成功'); router.push('/admin/jobs')
    }
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

function goBack() { router.push('/admin/jobs') }
onMounted(loadJob)
</script>

<template>
  <div class="job-edit">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="goBack">返回列表</el-button>
      <h2>{{ pageTitle }}</h2><div></div>
    </div>

    <el-card v-loading="loading">
      <el-form :model="form" label-width="100px" style="max-width: 960px">

        <el-form-item label="岗位名称" required>
          <el-input v-model="form.title" placeholder="如: Python后端开发工程师" />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="分类">
              <el-select v-model="form.category" style="width:100%">
                <el-option v-for="o in categoryOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="级别">
              <el-select v-model="form.level" style="width:100%">
                <el-option v-for="v in levelOptions" :key="v" :label="v" :value="v" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="薪资范围">
              <el-input v-model="form.salary_range" placeholder="如: 25k-40k" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="岗位描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="岗位职责描述..." />
        </el-form-item>

        <el-form-item label="技能标签">
          <el-input v-model="skillsText" type="textarea" :rows="2" placeholder="逗号分隔: Python, FastAPI, MySQL, Redis" />
          <span class="form-hint">用于快速匹配和搜索，逗号分隔</span>
        </el-form-item>

        <el-divider content-position="left">技能树</el-divider>

        <div class="skill-tree-editor">
          <div v-for="(domain, di) in domains" :key="di" class="domain-card">
            <div class="domain-header">
              <el-input v-model="domain.name" placeholder="领域，如: 数据库" style="width:160px" size="small" />
              <span class="weight-label">权重</span>
              <el-input-number v-model="domain.weight" :min="1" :max="999" size="small" style="width:80px" />
              <el-tag size="small" type="info">{{ weightPct[di] || 0 }}%</el-tag>
              <el-button :icon="Delete" size="small" type="danger" circle @click="removeDomain(di)" />
            </div>

            <!-- skills (level 2) -->
            <div v-for="(skill, si) in domain.skills" :key="si" class="skill-block">
              <div class="skill-row">
                <span class="tree-dot"></span>
                <el-input v-model="skill.name" placeholder="技能，如: 事务与锁" size="small" style="flex:1" />
                <el-select v-model="skill.level" size="small" style="width:80px">
                  <el-option v-for="v in diffOptions" :key="v" :label="v" :value="v" />
                </el-select>
                <el-button :icon="Delete" size="small" circle @click="removeSkill(di, si)" />
              </div>

              <!-- children (level 3, optional) -->
              <div v-if="skill.children" class="child-list">
                <div v-for="(child, ci) in skill.children" :key="ci" class="child-row">
                  <span class="tree-dot sub"></span>
                  <el-input v-model="child.name" placeholder="知识点，如: 隔离级别、MVCC" size="small" style="flex:1" />
                  <el-button :icon="Delete" size="small" circle @click="removeChild(di, si, ci)" />
                </div>
              </div>
              <el-button size="small" text type="primary" @click="addChild(di, si)" style="margin-left:20px">
                + 知识点
              </el-button>
            </div>

            <el-button size="small" :icon="Plus" @click="addSkill(di)">添加技能</el-button>
          </div>

          <el-button :icon="Plus" @click="addDomain">添加领域</el-button>
        </div>

        <el-divider />
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ isEdit ? '保存修改' : '创建岗位' }}
          </el-button>
          <el-button @click="goBack">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.job-edit { padding: 0 4px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; flex: 1; text-align: center; }
.form-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.skill-tree-editor { margin-bottom: 16px; }

.domain-card {
  background: #fafafa; border: 1px solid #e8e8e8;
  border-radius: 6px; padding: 12px 14px; margin-bottom: 10px;
}
.domain-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
  padding-bottom: 8px; border-bottom: 1px dashed #e8e8e8;
}
.weight-label { font-size: 12px; color: #909399; white-space: nowrap; }

.skill-block {
  margin-left: 4px; margin-bottom: 4px;
  padding: 4px 0 4px 8px;
  border-left: 2px solid #e8e8e8;
}
.skill-row {
  display: flex; align-items: center; gap: 6px; margin-bottom: 2px;
}

.child-list { margin: 2px 0 4px 16px; }
.child-row {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 2px; padding-left: 4px;
  border-left: 2px solid #d0d0f0;
}

.tree-dot {
  width: 7px; height: 7px; border-radius: 50%; background: #409eff; flex-shrink: 0;
}
.tree-dot.sub { width: 5px; height: 5px; background: #a0c4ff; }
</style>
