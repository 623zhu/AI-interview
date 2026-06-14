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
  question_number: number
  total_questions: number
}

export const useInterviewStore = defineStore('interview', () => {
  const sessionId = ref<string | null>(null)
  const status = ref<'idle' | 'active' | 'completed'>('idle')
  const messages = ref<Message[]>([])
  const currentQuestion = ref<Question | null>(null)
  const currentQuestionIndex = ref(0)
  const totalQuestions = ref(0)
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
    currentQuestionIndex.value = 0
    totalQuestions.value = 0
    duration.value = 0
  }

  return {
    sessionId,
    status,
    messages,
    currentQuestion,
    currentQuestionIndex,
    totalQuestions,
    duration,
    addMessage,
    setSession,
    reset,
  }
})
