<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    :title="editData ? '编辑交换机' : '添加交换机'"
    width="520px"
    @open="initForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="交换机名称" />
      </el-form-item>
      <el-form-item label="IP 地址" prop="ip_address">
        <el-input v-model="form.ip_address" placeholder="管理 IP" :disabled="!!editData" />
      </el-form-item>
      <el-form-item label="SNMP 团体字" prop="community">
        <el-input v-model="form.community" placeholder="community" />
      </el-form-item>
      <el-form-item label="MIB 类型" prop="mib_type">
        <el-radio-group v-model="form.mib_type">
          <el-radio value="standard">标准 MIB</el-radio>
          <el-radio value="huawei">华为私有 MIB</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="SNMP 端口" prop="snmp_port">
        <el-input-number v-model="form.snmp_port" :min="1" :max="65535" />
      </el-form-item>
      <el-form-item label="超时 (秒)" prop="snmp_timeout">
        <el-input-number v-model="form.snmp_timeout" :min="1" :max="30" />
      </el-form-item>
      <el-form-item label="重试次数" prop="snmp_retries">
        <el-input-number v-model="form.snmp_retries" :min="0" :max="10" />
      </el-form-item>
      <el-form-item label="扫描间隔 (秒)">
        <el-input-number v-model="form.scan_interval" :min="0" :max="86400" />
        <span class="hint">0 = 仅手动扫描</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { createSwitch, updateSwitch } from '@/api/switches'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  editData: Object,
})
const emit = defineEmits(['update:visible', 'saved'])

const formRef = ref()
const submitting = ref(false)
const form = reactive({
  name: '',
  ip_address: '',
  community: '',
  mib_type: 'standard',
  snmp_port: 161,
  snmp_timeout: 3,
  snmp_retries: 2,
  scan_interval: 3600,
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  ip_address: [{ required: true, message: '请输入 IP 地址', trigger: 'blur' }],
  community: [{ required: true, message: '请输入 SNMP 团体字', trigger: 'blur' }],
}

function initForm() {
  Object.assign(form, {
    name: props.editData?.name || '',
    ip_address: props.editData?.ip_address || '',
    community: props.editData?.community || '',
    mib_type: props.editData?.mib_type || 'standard',
    snmp_port: props.editData?.snmp_port ?? 161,
    snmp_timeout: props.editData?.snmp_timeout ?? 3,
    snmp_retries: props.editData?.snmp_retries ?? 2,
    scan_interval: props.editData?.scan_interval ?? 3600,
  })
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (props.editData) {
      await updateSwitch(props.editData.id, { ...form })
      ElMessage.success('已更新')
    } else {
      await createSwitch({ ...form })
      ElMessage.success('已添加')
    }
    emit('saved')
    emit('update:visible', false)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
