<script setup lang="ts">
import UserHeader from '@/components/layout/user/UserHeader.vue'
</script>

<template>
  <div class="user-layout">
    <UserHeader />
    <main class="user-layout__content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.user-layout {
  min-height: 100vh;
  background: var(--el-bg-color-page);
}

.user-layout__content {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
}
</style>
