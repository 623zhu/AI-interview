<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'

const router = useRouter()
const appStore = useAppStore()
</script>

<template>
  <el-aside :width="appStore.adminSidebarCollapsed ? '64px' : '220px'" class="admin-sidebar">
    <div class="admin-sidebar__logo">
      <router-link to="/admin/questions">
        {{ appStore.adminSidebarCollapsed ? '' : 'AI-Interview' }}
      </router-link>
    </div>
    <el-menu
      :default-active="router.currentRoute.value.path"
      :collapse="appStore.adminSidebarCollapsed"
      router
      background-color="#001529"
      text-color="#ffffffb3"
      active-text-color="#fff"
      class="admin-sidebar__menu"
    >
      <el-sub-menu index="questions-group">
        <template #title>
          <el-icon><EditPen /></el-icon>
          <span>题库管理</span>
        </template>
        <el-menu-item index="/admin/questions">题目列表</el-menu-item>
        <el-menu-item index="/admin/questions/create">新增题目</el-menu-item>
        <el-menu-item index="/admin/questions/import">导入题目</el-menu-item>
      </el-sub-menu>
      <el-menu-item index="/admin/jobs">
        <el-icon><Briefcase /></el-icon>
        <span>岗位管理</span>
      </el-menu-item>
      <el-menu-item index="/admin/users">
        <el-icon><User /></el-icon>
        <span>用户管理</span>
      </el-menu-item>
      <el-menu-item index="/admin/analytics">
        <el-icon><TrendCharts /></el-icon>
        <span>数据统计</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style scoped>
.admin-sidebar {
  background-color: #001529;
  min-height: 100vh;
  transition: width 0.3s;
  overflow-x: hidden;
}

.admin-sidebar__logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

.admin-sidebar__logo a {
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}

.admin-sidebar__menu {
  border-right: none !important;
}
</style>
