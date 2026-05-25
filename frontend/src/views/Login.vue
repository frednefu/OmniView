<template>
  <div class="login-container">
    <!-- 装饰背景 -->
    <div class="bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>

    <div class="login-card">
      <div class="login-header">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
          <rect width="24" height="24" rx="6" fill="url(#login-logo-grad)"/>
          <text x="12" y="17" text-anchor="middle" fill="#fff" font-size="11" font-weight="700">OV</text>
          <defs>
            <linearGradient id="login-logo-grad" x1="0" y1="0" x2="24" y2="24">
              <stop stop-color="#6366f1"/>
              <stop offset="1" stop-color="#8b5cf6"/>
            </linearGradient>
          </defs>
        </svg>
        <h1>OmniView</h1>
        <p>全维 IT 资产发现与治理平台</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" size="large" @submit.prevent="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" native-type="submit" class="login-btn">
            {{ loading ? '验证中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="login-footer">
      <span>默认管理员: admin / Admin123!</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 40%, #312e81 70%, #1e1b4b 100%);
  position: relative;
  overflow: hidden;
}

/* 装饰背景形状 */
.bg-shapes {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
.shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.08;
}
.shape-1 {
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, #6366f1, transparent);
  top: -200px;
  right: -150px;
}
.shape-2 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, #8b5cf6, transparent);
  bottom: -100px;
  left: -100px;
}
.shape-3 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, #a78bfa, transparent);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.login-card {
  width: 400px;
  padding: 44px 40px 36px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: var(--radius-lg);
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.4);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.login-header h1 {
  font-size: 24px;
  color: var(--color-text);
  margin: 14px 0 4px;
  font-weight: 700;
  letter-spacing: 2px;
}

.login-header p {
  color: var(--color-text-muted);
  margin: 0;
  font-size: 14px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  letter-spacing: 4px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--color-primary), #8b5cf6);
  border: none;
  transition: all var(--transition-normal);
}

.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35);
}

.login-footer {
  position: relative;
  z-index: 1;
  margin-top: 20px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  text-align: center;
}
</style>
