<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { jobApi } from '@/api/jobs'
import type { JobListItem } from '@/types/job'

const router = useRouter()

// ── State ──
const loading = ref(false)
const list = ref<JobListItem[]>([])
const total = ref(0)

const filters = reactive({
  keyword: '',
  category: '',
  level: '',
  page: 1,
  page_size: 15,
})

const categoryOptions = [
  { label: '前端 (frontend)', value: 'frontend' },
  { label: '后端 (backend)', value: 'backend' },
  { label: '全栈 (fullstack)', value: 'fullstack' },
  { label: '数据 (data)', value: 'data' },
  { label: 'AI应用 (ai)', value: 'ai' },
  { label: '运维 (devops)', value: 'devops' },
  { label: '测试 (qa)', value: 'qa' },
]

const levelOptions = [
  { label: '初级', value: 'junior' },
  { label: '中级', value: 'mid' },
  { label: '高级', value: 'senior' },
  { label: 'Leader', value: 'lead' },
]

// ── Methods ──
async function fetchList() {
  loading.value = true
  try {
    const res = await jobApi.list({
      page: filters.page,
      page_size: filters.page_size,
      category: filters.category || undefined,
      level: filters.level || undefined,
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
  router.push('/admin/jobs/create')
}

function goEdit(id: string) {
  router.push(`/admin/jobs/${id}/edit`)
}

async function toggleJob(row: JobListItem) {
  try {
    const res = await jobApi.toggle(row.id)
    const msg = res.data.data.is_active ? '已启用' : '已禁用'
    ElMessage.success(msg)
    row.is_active = res.data.data.is_active
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

async function deleteJob(row: JobListItem) {
  try {
    await ElMessageBox.confirm(`确定删除岗位 "${row.title}"？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await jobApi.delete(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || '删除失败')
    }
  }
}

onMounted(fetchList)
</script>

<template>
  <div class="job-manage">
    <!-- Header -->
    <div class="page-header">
      <h2>岗位管理</h2>
      <div class="header-actions">
        <el-button type="primary" :icon="Plus" @click="goCreate">新增岗位</el-button>
      </div>
    </div>

    <!-- Search bar -->
    <el-card class="search-bar">
      <el-form :inline="true" :model="filters" @submit.prevent="onSearch">
        <el-form-item label="关键词">
          <el-input
            v-model="filters.keyword"
            placeholder="搜索岗位名称..."
            clearable
            style="width: 220px"
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="filters.category" placeholder="全部分类" clearable style="width: 160px" @change="onSearch">
            <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="filters.level" placeholder="全部级别" clearable style="width: 120px" @change="onSearch">
            <el-option v-for="opt in levelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">搜索</el-button>
          <el-button @click="filters.keyword = ''; filters.category = ''; filters.level = ''; onSearch()">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Table -->
    <el-card>
      <el-table :data="list" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="title" label="岗位名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-switch :model-value="row.is_active" @click="toggleJob(row)" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="goEdit(row.id)">编辑</el-button>
            <el-button size="small" type="danger" @click="deleteJob(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="filters.page"
          :page-size="filters.page_size"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.job-manage {
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
  padding-bottom: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
