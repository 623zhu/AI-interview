<template>
  <div class="interview-history">
    <h2 class="page-title">📊 面试记录</h2>

    <!-- Summary -->
    <div class="summary-bar">
      <div class="summary-bar__item">
        <span class="summary-bar__num">{{ total }}</span>
        <span class="summary-bar__label">面试次数</span>
      </div>
      <div class="summary-bar__divider" />
      <div class="summary-bar__item">
        <span class="summary-bar__num">{{ avgScore ?? '--' }}</span>
        <span class="summary-bar__label">平均分</span>
      </div>
    </div>

    <!-- Table -->
    <el-card v-loading="loading">
      <el-table v-if="interviews.length" :data="interviews" stripe>
        <el-table-column prop="created_at" label="日期" width="140">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="job_title" label="岗位" min-width="140">
          <template #default="{ row }">{{ row.job_title || '未指定' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" text type="primary" size="small" @click="$router.push(`/report/${row.id}`)">
              查看报告
            </el-button>
            <el-button text type="danger" size="small" @click="deleteInterview(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="还没有面试记录" :image-size="80" />

      <!-- Pagination -->
      <div v-if="total > pageSize" class="pagination-wrap">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchInterviews"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import apiClient from '@/api/client'

const loading = ref(false)
const interviews = ref<any[]>([])
const total = ref(0)
const avgScore = ref<number | null>(null)
const currentPage = ref(1)
const pageSize = 20

async function fetchInterviews() {
  loading.value = true
  try {
    const { data: res } = await apiClient.get('/interviews', {
      params: { page: currentPage.value, page_size: pageSize }
    })
    const d = res.data
    interviews.value = d.items
    total.value = d.total

    // Calculate avg score from displayed items (or we could add a separate stat)
    const scored = d.items.filter((i: any) => i.score != null)
    if (scored.length) {
      avgScore.value = Math.round(scored.reduce((s: number, i: any) => s + i.score, 0) / scored.length * 10) / 10
    } else {
      avgScore.value = null
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function deleteInterview(row: any) {
  try {
    await ElMessageBox.confirm('确定要删除这条面试记录吗？删除后不可恢复。', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await apiClient.delete(`/interviews/${row.id}`)
    // If the deleted interview was the active one, clear localStorage
    const activeId = localStorage.getItem('active_interview')
    if (activeId === row.id) {
      localStorage.removeItem('active_interview')
      window.dispatchEvent(new CustomEvent('active-interview-cleared'))
    }
    ElMessage.success('已删除')
    fetchInterviews()
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function scoreClass(s: number) {
  if (s >= 80) return 'score-high'
  if (s >= 60) return 'score-mid'
  return 'score-low'
}

onMounted(() => fetchInterviews())
</script>

<style scoped>
.interview-history {
  max-width: 960px; margin: 0 auto;
}

.page-title {
  font-size: 22px;
  margin-bottom: 20px;
  color: #333;
}

/* Summary bar */
.summary-bar {
  display: flex;
  align-items: center;
  background: #fff;
  border-radius: 12px;
  padding: 16px 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.summary-bar__item {
  flex: 1;
  text-align: center;
}

.summary-bar__num {
  display: block;
  font-size: 28px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.summary-bar__label {
  font-size: 13px;
  color: #999;
  margin-top: 4px;
  display: block;
}

.summary-bar__divider {
  width: 1px;
  height: 36px;
  background: #ebeef5;
}

/* Table extras */
.progress-text {
  font-variant-numeric: tabular-nums;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* Score colors */
.score-high { color: #67c23a; font-weight: 700; font-size: 16px; }
.score-mid  { color: #e6a23c; font-weight: 700; font-size: 16px; }
.score-low  { color: #f56c6c; font-weight: 700; font-size: 16px; }
.score-na   { color: #ccc; font-size: 14px; }
</style>
