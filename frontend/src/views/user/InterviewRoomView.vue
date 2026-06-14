<template>
  <div class="interview-room">
    <!-- Header -->
    <header class="ir-header">
      <div class="ir-header__left">
        <span class="ir-header__title">{{ jobTitle || '模拟面试' }}</span>
      </div>
      <div class="ir-header__right">
        <el-button
          v-if="status === 'in_progress'"
          type="danger"
          size="small"
          plain
          :loading="ending"
          :disabled="ending"
          @click="handleEnd"
          style="margin-left: 12px"
        >
          {{ ending ? '生成报告中…' : '结束面试' }}
        </el-button>
      </div>
    </header>

    <!-- Chat area -->
    <main class="ir-chat" ref="chatRef">
      <div v-if="connecting" class="ir-chat__connecting">
        <el-icon :size="32" class="spin"><Loading /></el-icon>
        <p>正在连接面试官...</p>
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['ir-msg', `ir-msg--${msg.role}`]"
      >
        <div class="ir-msg__avatar">
          <div class="msg-avatar" :class="msg.role === 'ai' ? 'avatar-ai' : 'avatar-user'">
            {{ msg.role === 'ai' ? '✨' : '👤' }}
          </div>
        </div>
        <div class="ir-msg__body">
          <div class="ir-msg__role">{{ msg.role === 'ai' ? '面试官' : '我' }}</div>
          <div class="ir-msg__content" v-html="msg.content"></div>
        </div>
      </div>

      <!-- Thinking indicator -->
      <div v-if="thinking" class="ir-msg ir-msg--ai">
        <div class="ir-msg__avatar">
          <div class="msg-avatar avatar-ai">✨</div>
        </div>
        <div class="ir-msg__body">
          <div class="ir-msg__role">面试官</div>
          <div class="ir-msg__thinking">
            <span class="dot-pulse"></span>
          </div>
        </div>
      </div>
    </main>

    <!-- Input area -->
    <footer class="ir-input" v-if="status === 'in_progress'">
      <el-input
        v-model="inputText"
        :disabled="thinking"
        placeholder="输入你的回答..."
        maxlength="2000"
        show-word-limit
        type="textarea"
        :rows="3"
        @keydown.enter.exact.prevent="handleSend"
      />
      <div class="ir-input__actions">
        <button
          class="mic-toggle"
          :class="{ recording }"
          :disabled="thinking"
          @mousedown.prevent="startRecording"
          @mouseup.prevent="stopRecording"
          @mouseleave.prevent="stopRecording"
          @touchstart.prevent="startRecording"
          @touchend.prevent="stopRecording"
          title="按住说话"
        >
          {{ recording ? '🔴' : '🎤' }}
        </button>
        <el-button :disabled="thinking" @click="handleSkip">跳过此题</el-button>
        <el-button type="primary" :disabled="!inputText.trim() || thinking" :loading="thinking" @click="handleSend">发送 (Enter)</el-button>
      </div>
    </footer>

    <!-- Completed overlay -->
    <div v-if="status === 'completed'" class="ir-completed">
      <el-result icon="success" title="面试结束">
        <template #extra>
          <el-button type="primary" @click="$router.push(`/report/${sessionId}`)">
            查看报告
          </el-button>
          <el-button @click="$router.push('/interviews')">
            返回面试记录
          </el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const sessionId = route.params.id as string

// State
const status = ref<string>('created')
const jobTitle = ref('')
const currentQ = ref(1)
const totalQ = ref(7)
const connecting = ref(true)
const thinking = ref(false)
const inputText = ref('')
const messages = ref<{ role: string; content: string; _streaming?: boolean }[]>([])
const chatRef = ref<HTMLElement | null>(null)

// Voice input
const recording = ref(false)
let recognition: any = null

function startRecording() {
  if (thinking.value) return
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    ElMessage.warning('您的浏览器不支持语音识别，请使用 Chrome')
    return
  }
  recording.value = true
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = true
  recognition.continuous = true
  recognition.onresult = (e: any) => {
    let transcript = ''
    for (let i = 0; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript
    }
    inputText.value = transcript
  }
  recognition.onerror = () => { recording.value = false }
  recognition.onend = () => { recording.value = false }
  recognition.start()
}

function stopRecording() {
  if (!recording.value) return
  recording.value = false
  if (recognition) { recognition.stop(); recognition = null }
}

// TTS: speak AI questions
function speakText(text: string) {
  window.speechSynthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 0.9
  window.speechSynthesis.speak(utter)
}

let abortController: AbortController | null = null

// Load existing messages when resuming an interview
async function loadExistingMessages() {
  try {
    const res = await apiClient.get(`/interviews/${sessionId}/messages`)
    const msgs = res.data?.data || res.data || []
    for (const m of msgs) {
      messages.value.push({ role: m.role, content: m.content })
    }
    totalQ.value = msgs.length > 0 ? Math.max(2, Math.ceil(msgs.length / 2)) : 2
    scrollToBottom()
  } catch { /* ignore */ }
}

// Simulate streaming text output for pre-generated content
async function streamText(text: string, speed = 35) {
  messages.value.push({ role: 'ai', content: '', _streaming: true } as any)
  const idx = messages.value.length - 1
  for (let i = 0; i < text.length; i++) {
    messages.value[idx].content += text[i]
    if (i % 5 === 0) scrollToBottom()
    await new Promise(r => setTimeout(r, speed))
  }
  ;(messages.value[idx] as any)._streaming = false
  scrollToBottom()
}

// Scroll to bottom
function scrollToBottom() {
  nextTick(() => {
    if (chatRef.value) {
      chatRef.value.scrollTop = chatRef.value.scrollHeight
    }
  })
}

// Helper: POST + parse SSE stream
async function apiPost(path: string, body?: any) {
  const token = authStore.accessToken
  const res = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  return res
}

// Read SSE stream from fetch response
async function readSSEStream(response: Response) {
  const reader = response.body?.getReader()
  if (!reader) return

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const json = JSON.parse(line.slice(6))
          await handleSSEEvent(json)
        } catch { /* ignore */ }
      }
    }
  }
}

// Handle SSE events
async function handleSSEEvent(data: any) {
  const { event: evt, data: payload } = data || {}

  switch (evt) {
    case 'status':
      if (payload.status === 'thinking') {
        connecting.value = false
        thinking.value = true
      }
      break

    case 'token':
      thinking.value = false
      if (payload.content) {
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'ai' && last._streaming) {
          last.content += payload.content
        } else {
          messages.value.push({ role: 'ai', content: payload.content, _streaming: true } as any)
        }
        scrollToBottom()
        // Tiny delay to make streaming visible to the human eye
        await new Promise(r => setTimeout(r, 15))
      }
      break

    case 'question':
      thinking.value = false
      const lastAiQ = messages.value[messages.value.length - 1]
      if (lastAiQ) (lastAiQ as any)._streaming = false
      // Add message if not already streamed via token events
      if (payload.content && (!lastAiQ || lastAiQ.role !== 'ai' || lastAiQ.content !== payload.content)) {
        messages.value.push({ role: 'ai', content: payload.content })
      }
      if (payload.content) speakText(payload.content)
      if (payload.question_number) currentQ.value = payload.question_number
      if (payload.total_questions) totalQ.value = payload.total_questions
      scrollToBottom()
      break

    case 'score':
      // Evaluation feedback is stored for the report, NOT shown to candidate
      break

    case 'done':
      status.value = 'completed'
      thinking.value = false
      localStorage.removeItem('active_interview')
      abortController?.abort()
      // Navigate to report after short delay (let backend finish generating)
      setTimeout(() => {
        window.dispatchEvent(new Event('refresh-history'))
        router.push(`/report/${sessionId}`)
      }, 2000)
      break

    case 'error':
      ElMessage.error(payload.message || '发生错误')
      thinking.value = false
      break
  }
}

// Start the interview
async function startInterview() {
  try {
    const res = await apiPost(`/interviews/${sessionId}/start`)
    const json = await res.json()

    if (json.code === 200) {
      const d = json.data
      status.value = 'in_progress'
      connecting.value = false
      if (d.resume) {
        // Resume existing interview — load history messages
        await loadExistingMessages()
        return
      }
      currentQ.value = 1
      if (d.first_question) {
        totalQ.value = d.first_question.total_questions || 7
        await streamText(d.first_question.content)
      }
    } else if (res.status === 404) {
      localStorage.removeItem('active_interview')
      ElMessage.error('面试记录不存在或已被删除')
      router.push('/interviews')
    } else {
      ElMessage.error(json.message || '面试启动失败')
      router.push('/resume')
    }
  } catch (err: any) {
    if (err?.response?.status === 404 || err?.message?.includes('404')) {
      localStorage.removeItem('active_interview')
    }
    ElMessage.error('面试启动失败')
  }
}

// Send message & stream response
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || thinking.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  scrollToBottom()
  thinking.value = true

  try {
    abortController = new AbortController()
    const token = authStore.accessToken
    const res = await fetch(`/api/v1/interviews/${sessionId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: text }),
      signal: abortController.signal,
    })
    if (!res.ok) {
      if (res.status === 404) {
        localStorage.removeItem('active_interview')
        ElMessage.error('面试记录不存在或已被删除')
        status.value = 'completed'
      } else {
        ElMessage.error('请求失败')
      }
      return
    }
    await readSSEStream(res)
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      ElMessage.error('连接中断')
    }
  } finally {
    thinking.value = false
    abortController = null
  }
}

// Skip question
async function handleSkip() {
  try {
    const res = await apiPost(`/interviews/${sessionId}/skip`)
    const json = await res.json()
    if (json.code === 200) {
      currentQ.value = Math.min(currentQ.value + 1, totalQ.value)
      messages.value.push({ role: 'ai', content: '⏭ 已跳过此题' })
      if (json.data.next_question?.content) {
        messages.value.push({ role: 'ai', content: json.data.next_question.content })
      }
      scrollToBottom()
    }
  } catch {
    ElMessage.error('操作失败')
  }
}

// End interview
const ending = ref(false)

async function handleEnd() {
  try {
    await ElMessageBox.confirm('确定要结束面试吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  ending.value = true
  ElMessage.info('正在生成面试报告，请稍候…')
  try {
    const res = await apiPost(`/interviews/${sessionId}/end`)
    const json = await res.json()
    if (json.code === 200) {
      status.value = 'completed'
      localStorage.removeItem('active_interview')
      abortController?.abort()
      ElMessage.success('报告已生成')
    }
  } catch {
    ElMessage.error('操作失败')
  } finally {
    ending.value = false
  }
}

onMounted(() => {
  localStorage.setItem('active_interview', sessionId)
  startInterview()
})
watch(() => route.params.id, () => {
  window.location.reload()
})

onUnmounted(() => {
  abortController?.abort()
  if (status.value === 'completed') {
    localStorage.removeItem('active_interview')
  }
})
</script>

<style scoped>
.interview-room {
  display: flex; flex-direction: column;
  height: calc(100vh - 52px); background: #f8f9fa;
}

/* Header */
.ir-header {
  display: flex; align-items: center; justify-content: flex-end;
  padding: 8px 20px; flex-shrink: 0;
}

.ir-header__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ir-header__title {
  font-size: 16px;
  font-weight: 600;
}

.ir-header__center {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ir-header__progress {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.ir-header__right {
  display: flex;
  align-items: center;
}

/* Chat */
.ir-chat {
  flex: 1; overflow-y: auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 20px;
  max-width: 840px; margin: 0 auto; width: 100%;
}

.ir-chat__connecting {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  gap: 12px;
}

.ir-chat__connecting p {
  font-size: 14px;
}

/* Messages */
.ir-msg {
  display: flex;
  gap: 12px;
  max-width: 720px;
}

.ir-msg--ai {
  align-self: flex-start;
}

.ir-msg--user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.ir-msg__avatar {
  flex-shrink: 0;
}

.ir-msg__body {
  max-width: 600px;
}

.ir-msg__role {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}

.ir-msg--user .ir-msg__role {
  text-align: right;
}

.ir-msg__content {
  padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.7;
}
.ir-msg--ai .ir-msg__content { background: #f3f4f6; color: #1f2937; }
.ir-msg--user .ir-msg__content { background: #4f46e5; color: #fff; }

/* Thinking dots */
.ir-msg__thinking {
  background: #fff;
  padding: 12px 20px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.dot-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
  animation: dotPulse 1.2s infinite ease-in-out;
}

@keyframes dotPulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* Input */
.ir-input {
  padding: 16px 20px 20px; flex-shrink: 0;
  max-width: 840px; margin: 0 auto; width: 100%;
}

.ir-input__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

/* Completed */
.ir-completed {
  position: fixed;
  inset: 0;
  background: rgba(255,255,255,0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

/* Spin animation */
.spin {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Voice */
.mic-toggle {
  width: 32px; height: 32px; border-radius: 50%; border: 2px solid #dcdfe6;
  background: #fff; cursor: pointer; font-size: 16px; display: flex;
  align-items: center; justify-content: center; transition: all 0.2s;
  user-select: none; -webkit-user-select: none; padding: 0;
}
.mic-toggle:hover { border-color: var(--el-color-primary); }
.mic-toggle.recording { border-color: #f56c6c; background: #fef0f0; animation: pulse-mic 1.5s infinite; }
@keyframes pulse-mic { 0%,100%{ box-shadow: 0 0 0 0 rgba(245,108,108,0.4); } 50%{ box-shadow: 0 0 0 8px rgba(245,108,108,0); } }

.msg-avatar {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
}
.avatar-ai { background: #e0e7ff; color: #4f46e5; }
.avatar-user { background: #f3f4f6; color: #6b7280; }
</style>
