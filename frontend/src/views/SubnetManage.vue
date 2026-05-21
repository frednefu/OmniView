<template>
  <div class="subnet-manage">
    <div class="page-header">
      <h2>地址段管理</h2>
      <el-button type="primary" @click="openDialog()" v-if="authStore.isAdmin">
        <el-icon><Plus /></el-icon>添加地址段
      </el-button>
    </div>

    <el-table :data="subnets" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="subnet_cidr" label="CIDR" min-width="160" />
      <el-table-column prop="gateway" label="网关" min-width="130" />
      <el-table-column prop="vlan_id" label="VLAN ID" width="90">
        <template #default="{ row }">{{ row.vlan_id ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
      <el-table-column prop="is_managed" label="管理" width="70">
        <template #default="{ row }">
          <el-tag :type="row.is_managed ? 'success' : 'info'" size="small">
            {{ row.is_managed ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" v-if="authStore.isAdmin">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">编辑</el-button>
          <el-popconfirm title="确定删除此地址段？" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑地址段' : '添加地址段'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="CIDR" prop="subnet_cidr">
          <el-input v-model="form.subnet_cidr" placeholder="如 192.168.1.0/24" />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="如 办公网段" />
        </el-form-item>
        <el-form-item label="网关">
          <el-input v-model="form.gateway" placeholder="如 192.168.1.1" />
        </el-form-item>
        <el-form-item label="VLAN ID">
          <el-input-number v-model="form.vlan_id" :min="1" :max="4094" placeholder="可选" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="纳入管理">
          <el-switch v-model="form.is_managed" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { ElMessage } from 'element-plus'
import api from '@/api'

const authStore = useAuthStore()
const subnets = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const form = reactive({
  subnet_cidr: '',
  name: '',
  gateway: '',
  vlan_id: null,
  description: '',
  is_managed: true,
})

const rules = {
  subnet_cidr: [{ required: true, message: '请输入 CIDR', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

async function fetchSubnets() {
  loading.value = true
  try {
    const { data } = await api.get('/subnets')
    subnets.value = data
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

function resetForm() {
  form.subnet_cidr = ''
  form.name = ''
  form.gateway = ''
  form.vlan_id = null
  form.description = ''
  form.is_managed = true
}

function openDialog(row) {
  resetForm()
  if (row) {
    isEdit.value = true
    editId.value = row.id
    Object.assign(form, {
      subnet_cidr: row.subnet_cidr,
      name: row.name,
      gateway: row.gateway,
      vlan_id: row.vlan_id,
      description: row.description,
      is_managed: row.is_managed,
    })
  } else {
    isEdit.value = false
    editId.value = null
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (isEdit.value) {
      await api.put(`/subnets/${editId.value}`, { ...form })
      ElMessage.success('地址段已更新')
    } else {
      await api.post('/subnets', { ...form })
      ElMessage.success('地址段已创建')
    }
    dialogVisible.value = false
    fetchSubnets()
  } catch { /* handled by interceptor */ }
  finally { submitting.value = false }
}

async function handleDelete(id) {
  try {
    await api.delete(`/subnets/${id}`)
    ElMessage.success('地址段已删除')
    fetchSubnets()
  } catch { /* handled by interceptor */ }
}

onMounted(fetchSubnets)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
}
</style>
