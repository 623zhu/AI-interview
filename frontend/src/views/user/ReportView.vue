<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const reportId = computed(() => route.params.id as string)
const loading = ref(true)

interface Round {
  question: string
  answer: string
  comment: string
}

const report = ref<{ full_report: string; question_evaluations: Round[] } | null>(null)

const rounds = computed(() => report.value?.question_evaluations || [])

async function fetchReport() {
  loading.value = true
  try {
    const token = authStore.accessToken
    const res = await fetch(`/api/v1/reports/by-session/${reportId.value}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) {
      const json = await res.json()
      if (json.code === 200) report.value = json.data
      else ElMessage.error('报告不存在')
    }
  } catch { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

onMounted(() => {
  fetchReport()
  window.dispatchEvent(new Event('refresh-history'))
})
watch(reportId, () => {
  fetchReport()
  window.dispatchEvent(new Event('refresh-history'))
})
</script>

<template>
  <div class="report-chat" v-loading="loading">
    <template v-if="report">
      <div class="report-header">
        <h2>面试回顾</h2>
        <p class="report-sub">共 {{ rounds.length }} 轮对话</p>
      </div>

      <div class="chat-list">
        <template v-for="(q, i) in rounds" :key="i">
          <div class="round-block">
            <!-- Question -->
            <div class="chat-msg left">
              <div class="chat-avatar avatar-ai">✨</div>
              <div class="chat-bubble q-bubble">
                <div class="bubble-label">面试官</div>
                <div class="bubble-text">{{ q.question }}</div>
              </div>
            </div>

            <!-- Answer -->
            <div class="chat-msg right" v-if="q.answer">
              <div class="chat-avatar avatar-user">👤</div>
              <div class="chat-bubble a-bubble">
                <div class="bubble-label">你</div>
                <div class="bubble-text">{{ q.answer }}</div>
              </div>
            </div>

            <!-- Comment -->
            <div v-if="q.comment" class="chat-msg left eval-msg">
              <div class="chat-avatar avatar-eval">💬</div>
              <div class="chat-bubble eval-bubble">
                <div class="bubble-text">{{ q.comment }}</div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.report-chat { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }

.report-header { text-align: center; margin-bottom: 32px; }
.report-header h2 { font-size: 24px; color: #1f2937; margin: 0 0 4px; }
.report-sub { font-size: 14px; color: #9ca3af; margin: 0; }

.round-block { margin-bottom: 24px; }

.chat-list { display: flex; flex-direction: column; gap: 12px; }
.chat-msg { display: flex; gap: 10px; max-width: 680px; }
.chat-msg.left { align-self: flex-start; }
.chat-msg.right { align-self: flex-end; flex-direction: row-reverse; }

.chat-avatar { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; }
.avatar-ai { background: #e0e7ff; color: #4f46e5; }
.avatar-user { background: #f3f4f6; color: #6b7280; }
.avatar-eval { background: #e8f5e9; color: #43a047; }

.chat-bubble { padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.7; max-width: 580px; }
.q-bubble { background: #f3f4f6; color: #1f2937; }
.a-bubble { background: #4f46e5; color: #fff; }
.bubble-label { font-size: 11px; margin-bottom: 4px; opacity: 0.6; }
.bubble-text { white-space: pre-wrap; }

.eval-msg { margin-top: 2px; margin-bottom: 0; }
.eval-bubble { background: #e8f5e9; border: 1px solid #c8e6c9; }
</style>
