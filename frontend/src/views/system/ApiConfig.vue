<template>
  <div class="api-config-page">
    <div class="page-header">
      <h2>API 配置</h2>
      <span class="subtitle">配置外部数据中台 API 连接参数</span>
    </div>

    <el-card class="config-card">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        style="max-width: 640px"
        :disabled="submitting"
      >
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：学校数据中台" />
        </el-form-item>
        <el-form-item label="API 基础地址" prop="base_url">
          <el-input v-model="form.base_url" placeholder="https://dgp.nefu.edu.cn" />
        </el-form-item>
        <el-form-item label="APP KEY" prop="app_key">
          <el-input v-model="form.app_key" placeholder="数据中台分配的 KEY" show-password type="password" />
        </el-form-item>
        <el-form-item label="APP SECRET" prop="app_secret">
          <el-input v-model="form.app_secret" placeholder="数据中台分配的 SECRET" show-password type="password" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
          <el-button :loading="testing" @click="handleTest">测试连接</el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <div class="status-section">
        <div class="status-title">连接状态</div>
        <div class="status-row">
          <el-tag :type="testResult ? (testResult.success ? 'success' : 'danger') : 'info'" size="large">
            {{ testResult ? (testResult.success ? '连接正常' : '连接失败') : '未测试' }}
          </el-tag>
          <span v-if="testResult?.success && testResult.token_expires_in" class="status-extra">
            Token 有效期剩余 {{ Math.floor(testResult.token_expires_in / 60) }} 分钟
          </span>
          <span v-if="testResult && !testResult.success" class="status-error">{{ testResult.message }}</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfig, saveConfig, testConfig } from '@/api/apiConfig'
import 'element-plus/es/components/card/style/css'

const formRef = ref(null)
const submitting = ref(false)
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)

const form = reactive({
  name: '',
  base_url: '',
  app_key: '',
  app_secret: '',
})

const rules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  base_url: [{ required: true, message: '请输入 API 基础地址', trigger: 'blur' }],
  app_key: [{ required: true, message: '请输入 APP KEY', trigger: 'blur' }],
  app_secret: [{ required: true, message: '请输入 APP SECRET', trigger: 'blur' }],
}

async function loadConfig() {
  try {
    const cfg = await getConfig()
    form.name = cfg.name || ''
    form.base_url = cfg.base_url || ''
    form.app_key = cfg.app_key || ''
    form.app_secret = cfg.app_secret || ''
  } catch (e) {
    if (e.response?.status !== 404) {
      ElMessage.error('加载配置失败')
    }
  }
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    await saveConfig({ ...form })
    ElMessage.success('配置已保存')
    testResult.value = null
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const res = await testConfig()
    testResult.value = res
    if (res.success) {
      ElMessage.success('连接测试成功')
    } else {
      ElMessage.error(res.message || '连接测试失败')
    }
  } catch (e) {
    testResult.value = { success: false, message: '测试请求失败' }
    ElMessage.error('测试请求失败')
  } finally {
    testing.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.api-config-page {
  padding: 20px;
}
.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0 0 4px 0;
  font-size: 20px;
}
.subtitle {
  color: #909399;
  font-size: 13px;
}
.config-card {
  max-width: 800px;
}
.status-section {
  padding: 4px 0;
}
.status-title {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 10px;
  color: #303133;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.status-extra {
  color: #67c23a;
  font-size: 13px;
}
.status-error {
  color: #f56c6c;
  font-size: 13px;
}
</style>
