import { defineStore } from 'pinia'
import { ref } from 'vue'

interface Message {
  role: 'ai' | 'user' | 'system'
  content: string
  timestamp?: string
}

interface Question {
  id: string
  content: string
  category: string
  turn_number: number
  answered_count: number
}

export const useInterviewStore = defineStore('interview', () => {
  const sessionId = ref<string | null>(null)
  const status = ref<'idle' | 'active' | 'completed'>('idle')
  const messages = ref<Message[]>([])
  const currentQuestion = ref<Question | null>(null)
  const turnNumber = ref(0)
  const answeredCount = ref(0)
  const duration = ref(0)

  function addMessage(msg: Message) {
    messages.value.push(msg)
  }

  function setSession(id: string) {
    sessionId.value = id
  }

  function reset() {
    sessionId.value = null
    status.value = 'idle'
    messages.value = []
    currentQuestion.value = null
    turnNumber.value = 0
    answeredCount.value = 0
    duration.value = 0
  }

  return {
    sessionId,
    status,
    messages,
    currentQuestion,
    turnNumber,
    answeredCount,
    duration,
    addMessage,
    setSession,
    reset,
  }
})
