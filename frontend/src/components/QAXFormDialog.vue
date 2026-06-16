<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="isEdit ? '编辑椒图设备' : '添加椒图设备'"
    width="520px"
    @open="initForm"
  >
    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入名称" />
      </el-form-item>
      <el-form-item label="API 地址" prop="host">
        <el-input v-model="form.host" :disabled="isEdit" placeholder="如 https://10.10.11.30" />
      </el-form-item>
      <el-form-item label="账号 UUID" prop="uuid">
        <el-input v-model="form.uuid" placeholder="API 账号 UUID" />
      </el-form-item>
      <el-form-item label="授权密钥" prop="secret">
        <el-input v-model="form.secret" type="password" show-password :placeholder="isEdit ? '留空则不修改' : '请输入密钥'" />
      </el-form-item>
      <el-form-item label="扫描间隔">
        <el-input-number v-model="form.scan_interval" :min="0" :max="86400" :step="60" />
        <span class="form-hint">秒，0 = 仅手动扫描，默认 86400 (24小时)</span>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="footer-wrap">
        <div class="footer-left">
          <el-button @click="handleTest" :loading="testing">
            测试连接
          </el-button>
          <el-tag v-if="testResult" :type="testResult.ok ? 'success' : 'danger'" size="small" class="test-tag">
            {{ testResult.ok ? testResult.message : '连接失败' }}
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
import { createQAXDevice, updateQAXDevice, testQAXConnection } from '@/api/qax'
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
  uuid: '',
  secret: '',
  scan_interval: 86400,
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  host: [{ required: true, message: '请输入 API 地址', trigger: 'blur' }],
  uuid: [{ required: true, message: '请输入账号 UUID', trigger: 'blur' }],
  secret: [{ required: true, message: '请输入授权密钥', trigger: 'blur', validator: (r, v, cb) => {
    if (isEdit.value && !v) { cb() } else if (!v) { cb(new Error('请输入授权密钥')) } else { cb() }
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
    form.uuid = props.editData.uuid
    form.secret = props.editData.secret || ''
    form.scan_interval = props.editData.scan_interval ?? 86400
  } else {
    isEdit.value = false
    editId.value = null
    form.name = ''
    form.host = ''
    form.uuid = ''
    form.secret = ''
    form.scan_interval = 86400
  }
}

async function handleTest() {
  if (!form.host || !form.uuid) {
    ElMessage.warning('请先填写 API 地址和账号 UUID')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testQAXConnection({
      host: form.host,
      uuid: form.uuid,
      secret: form.secret,
    })
  } catch (e) {
    testResult.value = { ok: false, message: e?.response?.data?.detail || e?.message || '连接失败' }
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
      if (form.uuid !== props.editData.uuid) payload.uuid = form.uuid
      if (form.secret) payload.secret = form.secret
      if (form.scan_interval !== props.editData.scan_interval) payload.scan_interval = form.scan_interval
      await updateQAXDevice(editId.value, payload)
      ElMessage.success('椒图设备已更新')
    } else {
      await createQAXDevice({ ...form })
      ElMessage.success('椒图设备已创建')
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
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
