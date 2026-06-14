<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Upload, Search } from '@element-plus/icons-vue'
import { questionApi } from '@/api/questions'
import type { QuestionListItem } from '@/types/question'

const router = useRouter()

// ── State ──
const loading = ref(false)
const syncing = ref(false)
const list = ref<QuestionListItem[]>([])
const total = ref(0)
const selectedIds = ref<string[]>([])

const filters = reactive({
  keyword: '',
  category: '',
  difficulty: '',
  page: 1,
  page_size: 15,
})

const categoryOptions = [
  { label: '概念理解', value: 'concept' },
  { label: '原理理解', value: 'principle' },
  { label: '工程实践', value: 'practice' },
  { label: '优化能力', value: 'optimization' },
  { label: '系统设计', value: 'design' },
]

const difficultyOptions = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' },
]

const difficultyTagMap: Record<string, string> = {
  easy: 'success',
  medium: 'warning',
  hard: 'danger',
}

// ── Methods ──
async function fetchList() {
  loading.value = true
  try {
    const res = await questionApi.list({
      page: filters.page,
      page_size: filters.page_size,
      category: filters.category || undefined,
      difficulty: filters.difficulty || undefined,
      keyword: filters.keyword || undefined,
      include_inactive: true,
    })
    const d = res.data.data
    list.value = d.items
    total.value = d.total
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  filters.page = 1
  fetchList()
}

function onPageChange(page: number) {
  filters.page = page
  fetchList()
}

function goCreate() {
  router.push('/admin/questions/create')
}

function goEdit(id: string) {
  router.push(`/admin/questions/${id}`)
}

function goImport() {
  router.push('/admin/questions/import')
}

async function toggleQuestion(row: QuestionListItem) {
  try {
    const res = await questionApi.toggle(row.id)
    const msg = res.data.data.is_active ? '已启用' : '已禁用'
    ElMessage.success(msg)
    row.is_active = res.data.data.is_active
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function deleteQuestion(row: QuestionListItem) {
  try {
    await ElMessageBox.confirm(`确定删除题目："${row.content.slice(0, 40)}..."？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await questionApi.delete(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || '删除失败')
    }
  }
}

async function batchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的题目')
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 道题目？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await questionApi.batchDelete(selectedIds.value)
    ElMessage.success(`已删除 ${selectedIds.value.length} 道题目`)
    selectedIds.value = []
    fetchList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || '删除失败')
    }
  }
}

async function syncToChroma() {
  syncing.value = true
  try {
    const res = await questionApi.sync()
    ElMessage.success(res.data.message)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

function handleSelectionChange(rows: QuestionListItem[]) {
  selectedIds.value = rows.map(r => r.id)
}

// ── Lifecycle ──
onMounted(fetchList)
</script>

<template>
  <div class="question-manage">
    <!-- Header -->
    <div class="page-header">
      <h2>题库管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="goCreate">新增题目</el-button>
        <el-button :icon="Upload" @click="goImport">批量导入</el-button>
        <el-button :icon="Refresh" :loading="syncing" @click="syncToChroma">同步到向量库</el-button>
      </div>
    </div>

    <!-- Search bar -->
    <el-card class="search-bar">
      <el-form :inline="true" :model="filters" @submit.prevent="onSearch">
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            placeholder="搜索题目..."
            clearable
            style="width: 130px"
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="filters.category" placeholder="分类" clearable style="width: 130px" @change="onSearch">
            <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="filters.difficulty" placeholder="难度" clearable style="width: 100px" @change="onSearch">
            <el-option v-for="opt in difficultyOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">搜索</el-button>
          <el-button @click="filters.keyword = ''; filters.category = ''; filters.difficulty = ''; onSearch()">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Toolbar -->
    <div class="table-toolbar" v-if="selectedIds.length > 0">
      <span>已选 {{ selectedIds.length }} 项</span>
      <el-button type="danger" size="small" @click="batchDelete">批量删除</el-button>
    </div>

    <!-- Table -->
    <el-card>
      <el-table
        :data="list"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        stripe
        style="width: 100%"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column prop="content" label="题目内容" min-width="280" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="130">
          <template #default="{ row }">
            <el-tag>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="80">
          <template #default="{ row }">
            <el-tag :type="difficultyTagMap[row.difficulty] || 'info'" size="small">
              {{ row.difficulty === 'easy' ? '简单' : row.difficulty === 'medium' ? '中等' : '困难' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联技能" width="200">
          <template #default="{ row }">
            <div v-if="row.skill_nodes && row.skill_nodes.length" class="skill-tags">
              <el-tag v-for="s in row.skill_nodes.slice(0, 3)" :key="s" size="small" effect="plain" round>{{ s.split('/').pop() }}</el-tag>
              <el-tag v-if="row.skill_nodes.length > 3" size="small" type="info">+{{ row.skill_nodes.length - 3 }}</el-tag>
            </div>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="usage_count" label="使用次数" width="80" align="center" />
        <el-table-column width="220">
          <template #header><span style="display:block;text-align:center">操作</span></template>
          <template #default="{ row }">
            <div class="action-cell">
              <el-button size="small" @click="goEdit(row.id)">编辑</el-button>
              <el-switch :model-value="row.is_active" @click="toggleQuestion(row)" size="small" />
              <el-button size="small" type="danger" @click="deleteQuestion(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="filters.page"
          :page-size="filters.page_size"
          :total="total"
          layout="total, prev, pager, next, sizes"
          :page-sizes="[10, 15, 20, 50]"
          @current-change="onPageChange"
          @size-change="(s: number) => { filters.page_size = s; fetchList() }"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.skill-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.action-cell { display: flex; align-items: center; justify-content: center; gap: 8px; }
.text-muted { color: #c0c4cc; }

.question-manage {
  padding: 0 4px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.search-bar {
  margin-bottom: 16px;
}

.search-bar :deep(.el-card__body) {
  display: flex;
  align-items: center;
  padding-top: 12px;
  padding-bottom: 12px;
}

.search-bar :deep(.el-form) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.search-bar :deep(.el-form-item) {
  margin-right: 0;
  margin-bottom: 0;
}

.table-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  margin-bottom: 8px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: 14px;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
