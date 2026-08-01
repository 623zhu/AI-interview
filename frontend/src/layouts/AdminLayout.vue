<script setup lang="ts">
import AdminHeader from '@/components/layout/admin/AdminHeader.vue'
import AdminSidebar from '@/components/layout/admin/AdminSidebar.vue'
</script>

<template>
  <div class="admin-layout">
    <AdminSidebar />
    <div class="admin-layout__right">
      <AdminHeader />
      <main class="admin-layout__content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-layout {
  min-height: 100vh;
  display: flex;
  background: #f0f2f5;
}

.admin-layout__right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.admin-layout__content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
