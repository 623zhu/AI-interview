<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>AI-Interview 管理后台</h1>
        <p>管理员登录</p>
      </div>

      <el-form :model="form" label-position="top" @submit.prevent="handleSubmit">
        <el-form-item label="邮箱" :error="fieldErrors.email">
          <el-input
            v-model="form.email"
            placeholder="请输入管理员邮箱"
            :prefix-icon="Message"
            size="large"
            @input="fieldErrors.email = ''"
          />
        </el-form-item>

        <el-form-item label="密码" :error="fieldErrors.password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            @input="fieldErrors.password = ''"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" class="submit-btn" native-type="submit">
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Lock, Message } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const errorMsg = ref('')
const fieldErrors = reactive({ email: '', password: '' })

const form = reactive({
  email: '',
  password: '',
})

function validate(): boolean {
  fieldErrors.email = ''
  fieldErrors.password = ''
  let valid = true

  if (!form.email.trim()) {
    fieldErrors.email = '请输入邮箱'
    valid = false
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    fieldErrors.email = '邮箱格式不正确'
    valid = false
  }

  if (!form.password) {
    fieldErrors.password = '请输入密码'
    valid = false
  }

  return valid
}

async function handleSubmit() {
  if (!validate()) return
  loading.value = true
  errorMsg.value = ''

  try {
    await authStore.login(form.email, form.password)
    router.push('/admin/analytics')
  } catch (err: any) {
    const detail = err?.response?.data?.detail || '登录失败'
    errorMsg.value = typeof detail === 'string' ? detail : JSON.stringify(detail)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 40px 20px;
  background: #001529;
}

.login-card {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h1 {
  font-size: 24px;
  color: #333;
  margin: 0 0 8px;
}

.login-header p {
  color: #999;
  font-size: 14px;
  margin: 0;
}

.submit-btn {
  width: 100%;
}

.error-msg {
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
  margin-top: 8px;
}
</style>
