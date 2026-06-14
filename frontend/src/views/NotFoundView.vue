<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <div class="not-found">
    <h1>404</h1>
    <p>页面不存在</p>
    <el-button type="primary" @click="router.push('/resume')">返回首页</el-button>
  </div>
</template>

<style scoped>
.not-found {
  text-align: center;
  padding: 100px 20px;
}
.not-found h1 {
  font-size: 80px;
  color: var(--el-color-primary);
  margin-bottom: 16px;
}
.not-found p {
  font-size: 18px;
  color: #999;
  margin-bottom: 24px;
}
</style>
