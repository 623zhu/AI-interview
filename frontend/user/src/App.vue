<script setup lang="ts">
import { Setting } from '@element-plus/icons-vue'
import { ElButton, ElTooltip } from 'element-plus'
import 'element-plus/es/components/base/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/tooltip/style/css'


function openAdminClient(): void {
  window.location.assign('/admin.html')
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <a class="brand" href="/" aria-label="AI Interview 用户端首页">
        <span class="brand-mark">AI</span>
        <span>
          <strong>AI Interview</strong>
          <small>候选人端</small>
        </span>
      </a>

      <ElTooltip content="打开管理端" placement="bottom">
        <ElButton
          :icon="Setting"
          circle
          aria-label="打开管理端"
          @click="openAdminClient"
        />
      </ElTooltip>
    </header>

    <main class="workspace">
      <section class="workspace-heading">
        <p class="section-label">候选人工作台</p>
        <h1>我的面试</h1>
      </section>

      <section class="empty-state" aria-labelledby="empty-title">
        <span class="empty-icon">AI</span>
        <div>
          <h2 id="empty-title">暂无进行中的面试</h2>
          <p>登录注册接入后，面试会话将在这里展示。</p>
        </div>
      </section>
    </main>
  </div>
</template>
