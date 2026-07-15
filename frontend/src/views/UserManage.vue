<template>
  <div class="user-manage">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>添加用户
      </el-button>
    </div>

    <el-card>
      <div class="filter-bar">
        <el-input
          v-model="search"
          placeholder="搜索用户名或邮箱..."
          clearable
          style="width: 280px"
          @keyup.enter="fetchList"
          @clear="fetchList"
        />
        <el-button type="primary" @click="fetchList">查询</el-button>
      </div>

      <el-table :data="users" stripe v-loading="loading" style="width: 100%">
        <template #empty>
          <el-empty description="暂无用户" :image-size="80" />
        </template>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="160">
          <template #default="{ row }">
            {{ row.email || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="90">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="warning" @click="openResetPassword(row)">重置密码</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="page" :page-size="size" :total="total"
          layout="total, prev, pager, next" @current-change="fetchList" />
      </div>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑用户' : '添加用户'" width="480px" @close="resetForm">
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="isEdit" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱（选填）" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordDialogVisible" title="重置密码" width="420px">
      <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="80px">
        <el-form-item label="用户">
          <span>{{ passwordTarget?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="passwordForm.new_password" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleResetPassword" :loading="resetting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getUsers, createUser, updateUser, deleteUser, resetUserPassword } from '@/api/users'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatTime } from '@/utils/format'

const users = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({ username: '', password: '', email: '', role: 'user' })
const formRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const passwordDialogVisible = ref(false)
const passwordTarget = ref(null)
const resetting = ref(false)
const passwordFormRef = ref(null)
const passwordForm = reactive({ new_password: '' })
const passwordRules = {
  new_password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
}


async function fetchList() {
  loading.value = true
  try {
    const res = await getUsers({ page: page.value, size: size.value, search: search.value })
    users.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.username = ''
  form.password = ''
  form.email = ''
  form.role = 'user'
  isEdit.value = false
  editId.value = null
  formRef.value?.resetFields()
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  form.username = row.username
  form.email = row.email || ''
  form.role = row.role
  form.password = ''
  dialogVisible.value = true
}

async function handleSubmit() {
  try {
    await formRef.value.validate()
  } catch { return }
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateUser(editId.value, { email: form.email, role: form.role })
      ElMessage.success('用户已更新')
    } else {
      await createUser({ username: form.username, password: form.password, email: form.email || null, role: form.role })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    fetchList()
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户 ${row.username}？此操作不可恢复。`, '确认删除', { type: 'warning' })
    await deleteUser(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch { /* cancelled */ }
}

function openResetPassword(row) {
  passwordTarget.value = row
  passwordForm.new_password = ''
  passwordDialogVisible.value = true
  passwordFormRef.value?.resetFields()
}

async function handleResetPassword() {
  try {
    await passwordFormRef.value.validate()
  } catch { return }
  resetting.value = true
  try {
    await resetUserPassword(passwordTarget.value.id, passwordForm.new_password)
    ElMessage.success('密码已重置')
    passwordDialogVisible.value = false
  } finally {
    resetting.value = false
  }
}

onMounted(fetchList)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
