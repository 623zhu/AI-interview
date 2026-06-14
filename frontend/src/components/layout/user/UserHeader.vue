<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { VideoPlay } from '@element-plus/icons-vue'
import apiClient from '@/api/client'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeInterviewId = ref<string | null>(localStorage.getItem('active_interview'))

async function verifyActiveInterview() {
  const id = localStorage.getItem('active_interview')
  if (!id) {
    activeInterviewId.value = null
    return
  }
  try {
    await apiClient.get(`/interviews/${id}`)
    activeInterviewId.value = id
  } catch {
    localStorage.removeItem('active_interview')
    activeInterviewId.value = null
  }
}

function updateActiveInterview() {
  verifyActiveInterview()
}

function onStorage(e: StorageEvent) {
  if (e.key === 'active_interview') updateActiveInterview()
}

onMounted(() => {
  verifyActiveInterview()
  window.addEventListener('storage', onStorage)
  window.addEventListener('active-interview-cleared', updateActiveInterview)
})
onUnmounted(() => {
  window.removeEventListener('storage', onStorage)
  window.removeEventListener('active-interview-cleared', updateActiveInterview)
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-header class="user-header">
    <div class="user-header__left">
      <router-link to="/resume" class="user-header__logo">
        AI-Interview
      </router-link>
      <nav class="user-header__nav">
        <router-link to="/resume" class="nav-link" :class="{ active: route.path === '/resume' }">
          我的简历
        </router-link>
        <router-link to="/interviews" class="nav-link" :class="{ active: route.path === '/interviews' }">
          面试记录
        </router-link>
        <router-link
          v-if="activeInterviewId"
          :to="`/interview/${activeInterviewId}`"
          class="nav-link nav-link--active-interview"
        >
          <el-icon :size="14"><VideoPlay /></el-icon>
          进行中
        </router-link>
      </nav>
    </div>
    <div class="user-header__right">
      <el-dropdown v-if="authStore.isLoggedIn">
        <span class="user-header__user">
          <el-avatar :size="32" icon="UserFilled" />
          <span class="user-header__name">{{ authStore.user?.username }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-item v-if="authStore.isAdmin" @click="router.push('/admin/dashboard')">
            后台管理
          </el-dropdown-item>
          <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<style scoped>
.user-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
  height: 60px;
  padding: 0 24px;
}

.user-header__left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.user-header__logo {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
  text-decoration: none;
  white-space: nowrap;
}

.user-header__nav {
  display: flex;
  gap: 4px;
}

.nav-link {
  padding: 6px 14px;
  font-size: 14px;
  color: #555;
  text-decoration: none;
  border-radius: 6px;
  transition: all 0.2s;
}

.nav-link:hover {
  background: #f0f2f5;
  color: var(--el-color-primary);
}

.nav-link.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.nav-link--active-interview {
  color: var(--el-color-warning);
  display: flex;
  align-items: center;
  gap: 4px;
}

.nav-link--active-interview:hover,
.nav-link--active-interview.active {
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning);
}

.user-header__right {
  display: flex;
  align-items: center;
}

.user-header__user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.user-header__name {
  font-size: 14px;
}
</style>
