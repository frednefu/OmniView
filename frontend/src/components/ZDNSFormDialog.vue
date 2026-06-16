<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="isEdit ? '编辑 ZDNS 设备' : '添加 ZDNS 设备'"
    width="520px"
    @open="initForm"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入名称" />
      </el-form-item>
      <el-form-item label="主机地址" prop="host">
        <el-input v-model="form.host" :disabled="isEdit" placeholder="ZDNS 主机名或 IP" />
      </el-form-item>
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" placeholder="API 用户名" />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" show-password :placeholder="isEdit ? '留空则不修改' : '请输入密码'" />
      </el-form-item>
      <el-form-item label="端口" prop="port">
        <el-input-number v-model="form.port" :min="1" :max="65535" />
      </el-form-item>
      <el-form-item label="扫描间隔">
        <el-input-number v-model="form.scan_interval" :min="0" :max="86400" :step="60" />
        <span class="form-hint">秒，0 = 仅手动扫描</span>
      </el-form-item>
      <el-form-item label="IP扫描间隔">
        <el-input-number v-model="form.ip_scan_interval" :min="0" :max="86400" :step="60" />
        <span class="form-hint">秒，0 = 仅手动扫描</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="footer-wrap">
        <div class="footer-left">
          <el-button @click="handleTest" :loading="testing">
            测试连接
          </el-button>
          <el-tag v-if="testResult" :type="testResult.ok ? 'success' : 'danger'" size="small" class="test-tag">
            {{ testResult.ok ? '连接成功' : '连接失败' }}
          </el-tag>
        </div>
        <div class="footer-right">
          <el-button @click="$emit('update:visible', false)">取消</el-button>
          <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { createZDNSDevice, updateZDNSDevice, testZDNSConnection } from '@/api/zdns'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  editData: Object,
})
const emit = defineEmits(['update:visible', 'saved'])

const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const submitting = ref(false)
const testing = ref(false)
const testResult = ref(null)

const form = reactive({
  name: '',
  host: '',
  username: '',
  password: '',
  port: 20120,
  scan_interval: 86400,
  ip_scan_interval: 86400,
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  host: [{ required: true, message: '请输入主机地址', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur', validator: (r, v, cb) => {
    if (isEdit.value && !v) { cb() } else if (!v) { cb(new Error('请输入密码')) } else { cb() }
  }}],
}

function initForm() {
  formRef.value?.resetFields()
  testing.value = false
  testResult.value = null
  if (props.editData) {
    isEdit.value = true
    editId.value = props.editData.id
    form.name = props.editData.name
    form.host = props.editData.host
    form.username = props.editData.username
    form.password = props.editData.password || ''
    form.port = props.editData.port || 20120
    form.scan_interval = props.editData.scan_interval ?? 86400
    form.ip_scan_interval = props.editData.ip_scan_interval ?? 86400
  } else {
    isEdit.value = false
    editId.value = null
    form.name = ''
    form.host = ''
    form.username = ''
    form.password = ''
    form.port = 20120
    form.scan_interval = 86400
    form.ip_scan_interval = 86400
  }
}

async function handleTest() {
  if (!form.host || !form.username) {
    ElMessage.warning('请先填写主机地址和用户名')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testZDNSConnection({
      host: form.host,
      username: form.username,
      password: form.password,
      port: form.port,
    })
  } finally {
    testing.value = false
  }
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch { return }

  submitting.value = true
  try {
    if (isEdit.value) {
      const payload = {}
      if (form.name !== props.editData.name) payload.name = form.name
      if (form.username !== props.editData.username) payload.username = form.username
      if (form.password) payload.password = form.password
      if (form.port !== props.editData.port) payload.port = form.port
      if (form.scan_interval !== props.editData.scan_interval) payload.scan_interval = form.scan_interval
      if (form.ip_scan_interval !== props.editData.ip_scan_interval) payload.ip_scan_interval = form.ip_scan_interval
      await updateZDNSDevice(editId.value, payload)
      ElMessage.success('ZDNS 设备已更新')
    } else {
      await createZDNSDevice({ ...form })
      ElMessage.success('ZDNS 设备已创建')
    }
    emit('saved')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.footer-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.footer-right {
  display: flex;
  gap: 10px;
}
.form-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.test-tag {
  flex-shrink: 0;
}
</style>
