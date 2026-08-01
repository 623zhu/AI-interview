<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, User, DataBoard, Medal, Document } from '@element-plus/icons-vue'
import { adminApi, type AdminDashboardData } from '@/api/admin'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent, GridComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  LineChart, BarChart, PieChart,
  TitleComponent, TooltipComponent, LegendComponent, GridComponent,
  CanvasRenderer,
])

const loading = ref(false)
const data = ref<AdminDashboardData | null>(null)
const error = ref('')

const summaryCards = computed(() => {
  if (!data.value) return []
  const s = data.value.summary
  return [
    { label: '用户总数', value: s.total_users, icon: User, color: '#409eff' },
    { label: '面试总数', value: s.total_interviews, icon: DataBoard, color: '#67c23a' },
    { label: '完成率', value: s.completion_rate + '%', icon: Medal, color: '#e6a23c' },
    { label: '题库数量', value: s.total_questions, icon: Document, color: '#909399' },
  ]
})

// Interview trend line chart
const interviewTrendOption = computed(() => {
  if (!data.value?.interview_trend?.length) return {}
  const dates = data.value.interview_trend.map(d => d.date)
  const counts = data.value.interview_trend.map(d => d.count)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: { rotate: 45, fontSize: 11 },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: '面试数', data: counts, type: 'line', smooth: true,
      areaStyle: { color: 'rgba(64, 158, 255, 0.15)' },
      lineStyle: { color: '#409eff', width: 2 },
      itemStyle: { color: '#409eff' },
    }],
  }
})

// User growth trend line chart
const userTrendOption = computed(() => {
  if (!data.value?.user_trend?.length) return {}
  const dates = data.value.user_trend.map(d => d.date)
  const counts = data.value.user_trend.map(d => d.count)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: { rotate: 45, fontSize: 11 },
    },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: '新增用户', data: counts, type: 'bar',
      barWidth: '50%',
      itemStyle: { color: '#67c23a', borderRadius: [3, 3, 0, 0] },
    }],
  }
})

// Job popularity horizontal bar
const jobPopOption = computed(() => {
  if (!data.value?.job_popularity?.length) return {}
  const items = [...data.value.job_popularity].reverse() // bottom-up for horizontal bar
  const names = items.map(r => r.title.length > 10 ? r.title.slice(0, 10) + '…' : r.title)
  const counts = items.map(r => r.count)
  const colors = counts.map((_, i) => {
    const palette = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#36cfc9', '#b37feb', '#ffc069']
    return palette[i % palette.length]
  })
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: names },
    series: [{
      name: '面试次数', type: 'bar', data: counts.map((v, i) => ({ value: v, itemStyle: { color: colors[i], borderRadius: [0, 4, 4, 0] } })),
      barWidth: '60%',
      label: { show: true, position: 'right', fontSize: 12 },
    }],
  }
})

// Category distribution pie
const categoryDistOption = computed(() => {
  if (!data.value?.category_distribution) return {}
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}题 ({d}%)' },
    legend: { bottom: '0%' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
      label: { show: true, formatter: '{b}\n{c}题' },
      data: data.value.category_distribution.map(d => ({ name: d.category, value: d.count })),
    }],
  }
})

const statusLabels: Record<string, string> = {
  created: '已创建', in_progress: '进行中', completed: '已完成', cancelled: '已取消',
}

function statusType(s: string) {
  return s === 'completed' ? 'success' : s === 'in_progress' ? 'warning' : 'info'
}

async function fetchData() {
  loading.value = true
  error.value = ''
  try {
    const res = await adminApi.getDashboard()
    if (res.data.code === 200) data.value = res.data.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载数据失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<template>
  <div class="analytics-view" v-loading="loading">
    <div class="page-header">
      <h2>数据统计</h2>
      <el-button :icon="Refresh" @click="fetchData" :loading="loading">刷新</el-button>
    </div>

    <template v-if="data">
      <!-- Summary Cards -->
      <el-row :gutter="16" class="summary-row">
        <el-col :xs="12" :sm="6" v-for="card in summaryCards" :key="card.label">
          <el-card shadow="hover" class="summary-card">
            <div class="summary-card__inner">
              <div class="summary-card__icon" :style="{ background: card.color }">
                <el-icon :size="22"><component :is="card.icon" /></el-icon>
              </div>
              <div class="summary-card__text">
                <div class="summary-card__value">{{ card.value }}</div>
                <div class="summary-card__label">{{ card.label }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Charts Row 1: Interview Trend + User Growth -->
      <el-row :gutter="16">
        <el-col :xs="24" :lg="12">
          <el-card class="chart-card">
            <template #header><h3>面试趋势（近30天）</h3></template>
            <div style="height: 300px">
              <VChart :option="interviewTrendOption" autoresize />
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12">
          <el-card class="chart-card">
            <template #header><h3>用户增长（近30天）</h3></template>
            <div style="height: 300px">
              <VChart :option="userTrendOption" autoresize />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Charts Row 2: Job Popularity + Category Distribution -->
      <el-row :gutter="16">
        <el-col :xs="24" :lg="14">
          <el-card class="chart-card">
            <template #header><h3>岗位热度 Top 10</h3></template>
            <div :style="{ height: Math.max(280, data.job_popularity.length * 36 + 40) + 'px' }">
              <VChart :option="jobPopOption" autoresize />
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="10">
          <el-card class="chart-card">
            <template #header><h3>题目分类分布</h3></template>
            <div style="height: 300px">
              <VChart :option="categoryDistOption" autoresize />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- Recent Interviews -->
      <el-card class="chart-card">
        <template #header><h3>最近面试记录</h3></template>
        <el-table :data="data.recent_interviews" stripe size="small" empty-text="暂无记录">
          <el-table-column prop="username" label="用户" width="110" />
          <el-table-column prop="job_title" label="岗位" min-width="140" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">
                {{ statusLabels[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="160">
            <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-card v-if="error && !data" class="chart-card">
      <el-empty :description="error">
        <el-button type="primary" @click="fetchData">重试</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<style scoped>
.analytics-view { padding: 0 4px; }

.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px;
}
.page-header h2 { margin: 0; }

.summary-row { margin-bottom: 16px; }
.summary-card { margin-bottom: 12px; }

.summary-card__inner {
  display: flex; align-items: center; gap: 12px;
}

.summary-card__icon {
  width: 44px; height: 44px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
}

.summary-card__value {
  font-size: 24px; font-weight: 700; line-height: 1.2;
}
.summary-card__label { font-size: 13px; color: #909399; }

.chart-card { margin-bottom: 16px; }
.chart-card h3 { margin: 0; font-size: 15px; }
</style>
