<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>AI-Interview</h1>
        <p>AI 模拟面试平台</p>
      </div>

      <!-- Tab switcher -->
      <div class="login-tabs">
        <span :class="{ active: isLogin }" @click="isLogin = true">登录</span>
        <span :class="{ active: !isLogin }" @click="isLogin = false">注册</span>
      </div>

      <el-form
        :model="form"
        label-position="top"
        @submit.prevent="handleSubmit"
      >
        <!-- 注册时：用户名 -->
        <el-form-item v-if="!isLogin" label="用户名（字母、数字、下划线）" :error="fieldErrors.username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
            @input="fieldErrors.username = ''"
          />
        </el-form-item>

        <!-- 登录时：邮箱；注册时：邮箱 + 验证码 -->
        <el-form-item :label="isLogin ? '邮箱' : '邮箱'" :error="fieldErrors.email">
          <el-input
            v-model="form.email"
            :placeholder="isLogin ? '请输入邮箱' : '请输入邮箱地址'"
            :prefix-icon="Message"
            size="large"
            @input="fieldErrors.email = ''"
          />
        </el-form-item>

        <el-form-item v-if="!isLogin" label="验证码" :error="fieldErrors.code">
          <div class="code-row">
            <el-input
              v-model="form.code"
              placeholder="请输入6位验证码"
              size="large"
              maxlength="6"
              class="code-input"
              @input="fieldErrors.code = ''"
            />
            <el-button
              size="large"
              class="code-btn"
              :disabled="codeCountdown > 0 || codeSending"
              :loading="codeSending"
              @click="sendCode"
            >
              {{ codeCountdown > 0 ? `${codeCountdown}s` : '发送验证码' }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item :label="isLogin ? '密码' : '密码（至少8位）'" :error="fieldErrors.password">
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
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            class="submit-btn"
            native-type="submit"
          >
            {{ isLogin ? '登录' : '注册' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div v-if="errorMsg" class="error-msg">
        {{ errorMsg }}
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { User, Lock, Message } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const isLogin = ref(true)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  username: '',
  email: '',
  password: '',
  code: '',
})

// 手动控制字段错误
const fieldErrors = reactive({ username: '', password: '', email: '', code: '' })

// 验证码发送状态
const codeSending = ref(false)
const codeCountdown = ref(0)

// 手动校验
function validate(): boolean {
  fieldErrors.username = ''
  fieldErrors.password = ''
  fieldErrors.email = ''
  fieldErrors.code = ''
  let valid = true

  // 邮箱：登录和注册都必填
  if (!form.email.trim()) {
    fieldErrors.email = '请输入邮箱'
    valid = false
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    fieldErrors.email = '邮箱格式不正确'
    valid = false
  }

  // 用户名：仅注册时必填
  if (!isLogin.value) {
    if (!form.username.trim()) {
      fieldErrors.username = '请输入用户名'
      valid = false
    } else if (form.username.length < 2 || form.username.length > 50) {
      fieldErrors.username = '用户名长度 2-50'
      valid = false
    } else if (!/^[a-zA-Z0-9_]+$/.test(form.username)) {
      fieldErrors.username = '仅支持字母、数字、下划线'
      valid = false
    }
  }

  if (!form.password) {
    fieldErrors.password = '请输入密码'
    valid = false
  } else if (!isLogin.value && form.password.length < 8) {
    fieldErrors.password = '密码至少 8 位'
    valid = false
  }

  if (!isLogin.value) {
    if (!form.code.trim()) {
      fieldErrors.code = '请输入验证码'
      valid = false
    } else if (!/^\d{6}$/.test(form.code)) {
      fieldErrors.code = '验证码为6位数字'
      valid = false
    }
  }

  return valid
}

// 切换登录/注册时清空错误
watch(isLogin, () => {
  errorMsg.value = ''
  fieldErrors.username = ''
  fieldErrors.password = ''
  fieldErrors.email = ''
  fieldErrors.code = ''
  form.code = ''
  codeCountdown.value = 0
})

// 发送验证码
async function sendCode() {
  if (!form.email.trim()) {
    fieldErrors.email = '请先输入邮箱'
    return
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    fieldErrors.email = '邮箱格式不正确'
    return
  }

  codeSending.value = true
  try {
    await authApi.sendCode(form.email)
    ElMessage.success('验证码已发送')
    startCountdown()
  } catch (err: any) {
    const detail = err?.response?.data?.detail || '发送失败'
    ElMessage.error(typeof detail === 'string' ? detail : '发送失败')
  } finally {
    codeSending.value = false
  }
}

function startCountdown() {
  codeCountdown.value = 60
  const timer = setInterval(() => {
    codeCountdown.value--
    if (codeCountdown.value <= 0) {
      clearInterval(timer)
    }
  }, 1000)
}

async function handleSubmit() {
  if (!validate()) return

  loading.value = true
  errorMsg.value = ''

  try {
    if (isLogin.value) {
      await authStore.login(form.email, form.password)
      const redirect = (route.query.redirect as string) || (authStore.isAdmin ? '/admin/dashboard' : '/home')
      router.push(redirect)
    } else {
      await authStore.register(form.username, form.email, form.password, form.code)
      // Switch to login tab after successful registration
      isLogin.value = true
      errorMsg.value = ''
    }
  } catch (err: any) {
    const detail = err?.response?.data?.detail || err?.response?.data?.message || '操作失败'
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
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 24px;
}

.login-header h1 {
  font-size: 28px;
  color: #303133;
  margin-bottom: 4px;
}

.login-header p {
  font-size: 14px;
  color: #909399;
}

.login-tabs {
  display: flex;
  margin-bottom: 24px;
  border-bottom: 2px solid #ebeef5;
}

.login-tabs span {
  flex: 1;
  text-align: center;
  padding: 12px 0;
  cursor: pointer;
  font-size: 16px;
  color: #909399;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.3s;
}

.login-tabs span.active {
  color: #667eea;
  border-bottom-color: #667eea;
  font-weight: 600;
}

.submit-btn {
  width: 100%;
}

.code-row {
  display: flex;
  gap: 8px;
}

.code-input {
  flex: 0 0 58%;
}

.code-btn {
  flex: 1;
  white-space: nowrap;
}

.error-msg {
  background: #fef0f0;
  color: #f56c6c;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin-top: 8px;
}

.login-footer {
  text-align: center;
  margin-top: 12px;
}

.login-footer span {
  color: #999;
  font-size: 12px;
}
</style>
