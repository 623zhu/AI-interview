<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessageBox } from 'element-plus'
import apiClient from '@/api/client'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const collapsed = ref(false)
const history = ref<any[]>([])

async function fetchHistory() {
  try {
    const { data: res } = await apiClient.get('/interviews', { params: { page_size: 50 } })
    history.value = res.data.items || []
  } catch { /* ignore */ }
}

function goHistory(item: any) {
  if (item.status === 'completed') router.push(`/report/${item.id}`)
  else router.push(`/interview/${item.id}`)
}

function goHome() { router.push('/home') }

async function deleteInterview(id: string, e: Event) {
  e.stopPropagation()
  try {
    await ElMessageBox.confirm('确定要删除这条面试记录吗？', '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await apiClient.delete(`/interviews/${id}`)
    fetchHistory()
  } catch { /* cancelled */ }
}

function pageTitle() {
  if (route.path === '/home') return '开始新面试'
  if (route.path.startsWith('/interview/')) return '面试详情'
  if (route.path.startsWith('/report/')) return '面试报告'
  return ''
}

onMounted(fetchHistory)
watch(() => route.fullPath, () => fetchHistory())
// Allow child components to trigger refresh
window.addEventListener('refresh-history', fetchHistory)
</script>

<template>
  <div class="app-layout">
    <!-- Sidebar -->
    <aside :class="['sidebar', { collapsed }]">
      <div class="sidebar__brand">
        <div class="brand-icon">💬</div>
        <div v-if="!collapsed" class="brand-text">
          <div class="brand-name">AI 模拟面试</div>
          <div class="brand-sub">智能面试助手</div>
        </div>
      </div>

      <div class="sidebar__divider" />

      <div class="sidebar__action">
        <button class="new-btn" @click="goHome">
          <span>+</span>
          <span v-if="!collapsed">新面试</span>
        </button>
      </div>

      <div class="sidebar__divider" />

      <div v-if="!collapsed" class="sidebar__history">
        <div class="history-header">
          <span>历史记录</span>
          <span class="history-count">{{ history.length }}</span>
        </div>
        <div class="history-list">
          <div v-if="!history.length" class="history-empty">暂无面试记录</div>
          <div
            v-for="item in history"
            :key="item.id"
            :class="['history-item', { active: route.params.id === item.id }]"
            @click="goHistory(item)"
          >
            <div class="history-item__main">
              <div class="history-item__title">{{ item.job_title || '未指定岗位' }}</div>
              <div class="history-item__meta">
                <span :class="['status-dot', item.status]" />
                <span>{{ item.status === 'completed' ? '已完成' : '进行中' }}</span>
                <span>·</span>
                <span>{{ item.created_at?.slice(5, 10) }}</span>
              </div>
            </div>
            <button class="history-item__delete" @click="deleteInterview(item.id, $event)">🗑</button>
          </div>
        </div>
      </div>

      <div class="sidebar__spacer" />

      <div class="sidebar__footer">
        <div class="user-avatar">{{ authStore.user?.username?.charAt(0) || '?' }}</div>
        <div v-if="!collapsed" class="user-info">
          <div class="user-name">{{ authStore.user?.username }}</div>
          <div class="user-email">{{ authStore.user?.email }}</div>
        </div>
        <button v-if="!collapsed" class="logout-btn" @click="authStore.logout(); router.push('/login')" title="退出登录">↪</button>
      </div>
    </aside>

    <!-- Main -->
    <div class="main-area">
      <header class="topbar">
        <button class="sidebar-trigger" @click="collapsed = !collapsed">
          {{ collapsed ? '☰' : '☰' }}
        </button>
        <h2 class="topbar-title">{{ pageTitle() }}</h2>
      </header>
      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout { display: flex; height: 100vh; background: #f8f9fa; }
/* Sidebar */
.sidebar {
  width: 260px; flex-shrink: 0; display: flex; flex-direction: column;
  background: #fff; border-right: 1px solid #e5e7eb; transition: width 0.2s; overflow: hidden;
}
.sidebar.collapsed { width: 56px; }
.sidebar__brand { display: flex; align-items: center; gap: 12px; padding: 16px 14px; }
.brand-icon { font-size: 24px; flex-shrink: 0; }
.brand-name { font-size: 15px; font-weight: 600; color: #1f2937; }
.brand-sub { font-size: 11px; color: #9ca3af; margin-top: 1px; }
.sidebar__divider { height: 1px; background: #f3f4f6; margin: 0 12px; }
.sidebar__action { padding: 10px 14px; }
.new-btn {
  width: 100%; display: flex; align-items: center; gap: 8px;
  padding: 9px 14px; border: 1px solid #e5e7eb; border-radius: 8px;
  background: #fff; cursor: pointer; font-size: 14px; color: #374151;
  transition: all 0.15s; white-space: nowrap;
}
.new-btn:hover { background: #f3f4f6; border-color: #d1d5db; }
.new-btn span:first-child { font-size: 18px; font-weight: 300; }

.sidebar__history { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
.history-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 22px 6px; }
.history-header span:first-child { font-size: 12px; font-weight: 600; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
.history-count { font-size: 11px; color: #bbb; }
.history-list { flex: 1; overflow-y: auto; padding: 4px 8px; }
.history-empty { font-size: 12px; color: #bbb; text-align: center; padding: 32px 12px; }
.history-item {
  display: flex; align-items: center; padding: 8px 12px; border-radius: 8px;
  cursor: pointer; transition: background 0.1s; margin-bottom: 1px;
}
.history-item:hover { background: #f3f4f6; }
.history-item.active { background: #eff6ff; }
.history-item__main { flex: 1; min-width: 0; }
.history-item__title { font-size: 13px; font-weight: 500; color: #1f2937; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item__meta { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #9ca3af; margin-top: 2px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.status-dot.completed { background: #22c55e; }
.status-dot.in_progress { background: #f59e0b; }
.history-item__delete {
  opacity: 0; width: 24px; height: 24px; border: none; background: none;
  cursor: pointer; font-size: 12px; border-radius: 4px; display: flex;
  align-items: center; justify-content: center; transition: all 0.1s;
}
.history-item:hover .history-item__delete { opacity: 0.6; }
.history-item__delete:hover { opacity: 1 !important; background: #fee2e2; }

.sidebar__spacer { flex: 1; }
.sidebar__footer { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-top: 1px solid #f3f4f6; }
.user-avatar {
  width: 32px; height: 32px; border-radius: 50%; background: #e0e7ff; color: #4f46e5;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}
.user-name { font-size: 13px; font-weight: 500; color: #1f2937; }
.user-email { font-size: 11px; color: #9ca3af; }
.logout-btn { font-size: 14px; border: none; background: none; cursor: pointer; color: #9ca3af; padding: 4px; }
.logout-btn:hover { color: #ef4444; }

/* Main */
.main-area { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.topbar { display: flex; align-items: center; gap: 12px; height: 52px; padding: 0 20px; border-bottom: 1px solid #e5e7eb; background: #fff; flex-shrink: 0; }
.sidebar-trigger { width: 32px; height: 32px; border: none; background: none; cursor: pointer; font-size: 18px; color: #6b7280; border-radius: 6px; display: flex; align-items: center; justify-content: center; }
.sidebar-trigger:hover { background: #f3f4f6; }
.topbar-title { font-size: 17px; font-weight: 600; color: #1f2937; }
.main-content { flex: 1; overflow: auto; }
</style>
