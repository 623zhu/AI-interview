<script setup lang="ts">
import { Back } from '@element-plus/icons-vue'
import { ElButton, ElTooltip } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/tooltip/style/css'


function openUserClient(): void {
  window.location.assign('/')
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-topbar">
      <a class="admin-brand" href="/admin.html" aria-label="AI Interview 管理端首页">
        <span class="admin-brand-mark">AI</span>
        <span>
          <strong>AI Interview</strong>
          <small>管理端</small>
        </span>
      </a>

      <ElTooltip content="返回候选人端" placement="bottom">
        <ElButton
          :icon="Back"
          circle
          aria-label="返回候选人端"
          @click="openUserClient"
        />
      </ElTooltip>
    </header>

    <main class="admin-workspace">
      <section class="admin-heading">
        <p>运营工作台</p>
        <h1>管理概览</h1>
      </section>

      <section class="admin-empty" aria-labelledby="admin-empty-title">
        <span class="admin-empty-mark">A</span>
        <div>
          <h2 id="admin-empty-title">等待管理员认证接入</h2>
          <p>岗位、题库和用户数据将在后续模块中逐步加入。</p>
        </div>
      </section>
    </main>
  </div>
</template>
