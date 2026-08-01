<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-header class="admin-header">
    <el-breadcrumb separator="/">
      <el-breadcrumb-item :to="{ path: '/admin/dashboard' }">管理后台</el-breadcrumb-item>
      <el-breadcrumb-item v-if="router.currentRoute.value.meta.title">
        {{ router.currentRoute.value.meta.title }}
      </el-breadcrumb-item>
    </el-breadcrumb>
    <div class="admin-header__right">
      <el-dropdown>
        <span class="admin-header__user">
          <el-avatar :size="28" icon="UserFilled" />
          <span>{{ authStore.user?.username }}</span>
        </span>
        <template #dropdown>
          <el-dropdown-item @click="handleLogout">退出登录</el-dropdown-item>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<style scoped>
.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  height: 56px;
  padding: 0 24px;
  border-bottom: 1px solid #e8e8e8;
}

.admin-header__right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.admin-header__user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}
</style>
