<template>
  <div class="account-page">
    <div class="page-header">
      <h2>账号管理</h2>
      <div class="header-right">
        <el-select
          v-model="deptFilter"
          placeholder="按部门筛选"
          clearable
          filterable
          style="width: 200px"
          @change="fetchList"
        >
          <el-option
            v-for="d in deptOptions"
            :key="d.id"
            :label="d.dwmc"
            :value="d.id"
          />
        </el-select>
        <el-button type="primary" @click="openCreate">新建用户</el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="search"
        placeholder="搜索用户名 / 邮箱 / 工号"
        clearable
        style="width: 300px"
        @keyup.enter="fetchList"
        @clear="fetchList"
      >
        <template #append>
          <el-button :icon="Search" @click="fetchList" />
        </template>
      </el-input>
    </div>

    <!-- 用户列表 -->
    <div style="margin-bottom:10px" v-if="selectedIds.length > 0">
      <el-button type="danger" @click="handleBatchDelete">批量删除 ({{ selectedIds.length }})</el-button>
      <el-button type="warning" @click="handleBatchDisable">批量禁用 ({{ selectedIds.length }})</el-button>
      <el-button type="success" @click="handleBatchEnable">批量启用 ({{ selectedIds.length }})</el-button>
    </div>
    <el-table :data="users" v-loading="loading" stripe @selection-change="onSelect">
      <el-table-column type="selection" width="45" />
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="gh" label="工号" width="120" />
      <el-table-column prop="gender" label="性别" width="60" />
      <el-table-column prop="department_name" label="所属部门" min-width="160" show-overflow-tooltip />
      <el-table-column prop="email" label="邮箱" width="180" show-overflow-tooltip />
      <el-table-column prop="phone" label="办公电话" width="130" />
      <el-table-column prop="mobile" label="移动电话" width="130" />
      <el-table-column prop="role" label="角色" width="80">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'" size="small">
            {{ row.role === 'admin' ? '管理员' : '用户' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="70">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" size="small" @click="openResetPassword(row)">重置密码</el-button>
          <el-button link :type="row.is_active ? 'info' : 'success'" size="small" @click="handleToggleActive(row)">
            {{ row.is_active ? '禁用' : '启用' }}
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap" v-if="total > 0">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="fetchList"
        @current-change="fetchList"
      />
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑用户' : '新建用户'"
      width="640px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" :disabled="submitting">
        <!-- 新建：账号类型 -->
        <template v-if="!isEdit">
          <el-form-item label="账号类型">
            <el-radio-group v-model="form.user_type" @change="onUserTypeChange">
              <el-radio value="internal">本校</el-radio>
              <el-radio value="external">校外</el-radio>
            </el-radio-group>
          </el-form-item>
          <!-- 本校：教职工验证 -->
          <template v-if="form.user_type === 'internal'">
          <el-divider content-position="left">教职工信息验证</el-divider>
          <el-form-item label="工号">
            <el-input v-model="form.gh" placeholder="输入工号（可选）" style="width: 160px" />
          </el-form-item>
          <el-form-item label="姓名">
            <el-input v-model="form.lookup_xm" placeholder="输入姓名（可选）" style="width: 160px" />
            <el-button style="margin-left: 12px" :loading="lookingUp" @click="handleLookup">查询</el-button>
            <span class="lookup-hint">工号和姓名可只填一个，模糊匹配</span>
          </el-form-item>

          <!-- 多人选择列表 -->
          <div v-if="lookupResult && lookupResult.found && lookupResult.staff_list.length > 1" class="lookup-result">
            <el-alert title="匹配到多人，请选择为哪个人开设账号" type="info" :closable="false" show-icon />
            <el-radio-group v-model="selectedStaffIndex" class="staff-radio-group" @change="onStaffSelected">
              <el-radio
                v-for="(s, idx) in lookupResult.staff_list"
                :key="s.gh"
                :value="idx"
                class="staff-radio"
              >
                <span class="staff-option">
                  <strong>{{ s.xm }}</strong>
                  <span class="staff-meta">工号：{{ s.gh }} | 单位：{{ s.department_name || s.szdwbm || '-' }} | 科室：{{ s.szks || '-' }}</span>
                </span>
              </el-radio>
            </el-radio-group>
          </div>

          <!-- 单人结果直接回显 -->
          <div v-if="lookupResult && lookupResult.found && lookupResult.staff_list.length === 1" class="lookup-result">
            <el-alert title="教职工验证通过" type="success" :closable="false" show-icon />
            <el-descriptions :column="2" border size="small" style="margin-top: 12px">
              <el-descriptions-item label="工号">{{ selectedStaff.gh }}</el-descriptions-item>
              <el-descriptions-item label="姓名">{{ selectedStaff.xm }}</el-descriptions-item>
              <el-descriptions-item label="所在单位">{{ selectedStaff.department_name || selectedStaff.szdwbm || '-' }}</el-descriptions-item>
              <el-descriptions-item label="所在科室">{{ selectedStaff.szks || '-' }}</el-descriptions-item>
              <el-descriptions-item label="办公电话">{{ selectedStaff.bgdh || '-' }}</el-descriptions-item>
              <el-descriptions-item label="电子邮箱">{{ selectedStaff.dzyx || '-' }}</el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- 未找到 -->
          <div v-if="lookupResult && !lookupResult.found" class="lookup-result">
            <el-alert :title="lookupResult.message || '未找到匹配的教职工'" type="error" :closable="false" show-icon />
          </div>
          </template>
          <!-- 校外：单位信息 -->
          <template v-if="form.user_type === 'external'">
            <el-divider content-position="left">校外用户信息</el-divider>
            <el-form-item label="单位名称">
              <el-input v-model="form.company" placeholder="请输入单位名称" />
            </el-form-item>
            <el-form-item label="联系人">
              <el-input v-model="form.contact_person" placeholder="请输入联系人" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="选填" />
            </el-form-item>
          </template>
        </template>

        <!-- 账号设置 -->
        <el-divider content-position="left">账号设置</el-divider>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="登录用户名，默认为工号" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码">
          <div style="display:flex;gap:8px;width:100%">
            <el-input v-model="form.password" type="password" placeholder="留空则默认使用工号" show-password style="flex:1" />
            <el-button @click="generatePassword">生成</el-button>
          </div>
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.name" placeholder="自动从教职工信息填入" />
        </el-form-item>
        <el-form-item label="性别">
          <el-select v-model="form.gender" placeholder="性别" style="width:100px">
            <el-option label="男" value="男" />
            <el-option label="女" value="女" />
          </el-select>
        </el-form-item>
        <el-form-item label="工号" prop="gh">
          <el-input v-model="form.gh" placeholder="工号" :disabled="!isEdit && lookupVerified" style="width: 200px" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-tree-select
            v-model="form.department_id"
            :data="deptTreeData"
            :props="{ label: 'dwmc', value: 'id', children: 'children' }"
            placeholder="选择部门"
            clearable
            filterable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="选填" />
        </el-form-item>
        <el-form-item label="办公电话">
          <el-input v-model="form.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="移动电话">
          <el-input v-model="form.mobile" placeholder="选填" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 140px">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="passwordDialogVisible" title="重置密码" width="400px">
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="目标用户">
          <span>{{ passwordTarget?.username }}</span>
        </el-form-item>
        <el-form-item label="新密码" required>
          <div style="display:flex;gap:8px;width:100%">
            <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="请输入新密码" style="flex:1" />
            <el-button @click="passwordForm.new_password = generatePasswordValue()">生成</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="handleResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { getUsers, createUser, updateUser, deleteUser, batchDeleteUsers, batchDisableUsers, resetUserPassword } from '@/api/users'
import { lookupStaff } from '@/api/staff'
import { getDepartmentTree } from '@/api/departments'

const loading = ref(false)
const users = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const deptFilter = ref(null)
const deptOptions = ref([])
const deptTreeData = ref([])

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const lookingUp = ref(false)
const lookupResult = ref(null)
const selectedStaffIndex = ref(0)

const emptyForm = () => ({
  username: '',
  password: '',
  email: '',
  role: 'user',
  gh: '',
  name: '',
  gender: '',
  lookup_xm: '',
  department_id: null,
  phone: '',
  mobile: '',
  user_type: 'internal',
  company: '',
  contact_person: '',
  notes: '',
})

const form = reactive(emptyForm())

const selectedStaff = computed(() => {
  if (!lookupResult.value?.found || !lookupResult.value.staff_list.length) return null
  const idx = selectedStaffIndex.value
  return lookupResult.value.staff_list[idx] || lookupResult.value.staff_list[0]
})

const lookupVerified = computed(() => {
  if (form.user_type === 'external') return true
  return lookupResult.value?.found === true && selectedStaff.value !== null
})

function onUserTypeChange() {
  lookupResult.value = null
  selectedStaffIndex.value = 0
  if (form.user_type === 'external') {
    form.gh = ''
    form.lookup_xm = ''
  }
}

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const passwordDialogVisible = ref(false)
const passwordTarget = ref(null)
const resetting = ref(false)
const passwordForm = reactive({ new_password: '' })

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

async function loadDeptOptions() {
  try {
    const tree = await getDepartmentTree(true)
    deptTreeData.value = tree
    function flatten(nodes, result = []) {
      for (const n of nodes) {
        result.push({ id: n.id, dwmc: n.dwmc })
        if (n.children) flatten(n.children, result)
      }
      return result
    }
    deptOptions.value = flatten(tree)
  } catch { /* 静默失败 */ }
}

async function fetchList() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value, search: search.value }
    if (deptFilter.value) params.department_id = deptFilter.value
    const res = await getUsers(params)
    users.value = res.items
    total.value = res.total
  } catch (e) {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  lookupResult.value = null
  selectedStaffIndex.value = 0
  formRef.value?.resetFields()
}

function openCreate() {
  resetForm()
  isEdit.value = false
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  isEdit.value = true
  editId.value = row.id
  form.username = row.username
  form.email = row.email || ''
  form.role = row.role
  form.gh = row.gh || ''
  form.name = row.name || ''
  form.gender = row.gender || ''
  form.department_id = row.department_id
  form.phone = row.phone || ''
  form.mobile = row.mobile || ''
  form.user_type = row.user_type || 'internal'
  form.company = row.company || ''
  form.contact_person = row.contact_person || ''
  form.notes = row.notes || ''
  dialogVisible.value = true
}

function onStaffSelected() {
  const s = selectedStaff.value
  if (s) {
    form.username = s.gh || ''
    form.gh = s.gh || ''
    form.name = s.xm || ''
    form.email = s.dzyx || ''
    form.phone = s.bgdh || ''
    form.mobile = s.yddh || ''
    form.department_id = s.department_id || null
  }
}

async function handleLookup() {
  if (!form.gh && !form.lookup_xm) {
    ElMessage.warning('请至少输入工号或姓名')
    return
  }
  lookingUp.value = true
  lookupResult.value = null
  selectedStaffIndex.value = 0
  try {
    const res = await lookupStaff(form.gh, form.lookup_xm)
    lookupResult.value = res
    if (res.found && res.staff_list.length > 0) {
      if (res.staff_list.length === 1) {
        // 单人：自动选中，用户名默认工号，自动填充联系方式
        selectedStaffIndex.value = 0
        const s = res.staff_list[0]
        form.username = s.gh || ''
        form.gh = s.gh || ''
        form.name = s.xm || ''
        form.email = s.dzyx || ''
        form.phone = s.bgdh || ''
        form.mobile = s.yddh || ''
        form.department_id = s.department_id || null
        ElMessage.success('教职工验证通过')
      } else {
        ElMessage.info(`匹配到 ${res.staff_list.length} 人，请选择`)
      }
    } else {
      ElMessage.warning(res.message || '未找到匹配的教职工')
    }
  } catch (e) {
    lookupResult.value = { found: false, staff_list: [], message: '查询失败' }
    ElMessage.error('查询教职工失败')
  } finally {
    lookingUp.value = false
  }
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const payload = {
      email: form.email || null,
      role: form.role,
      gh: form.gh || null,
      name: form.name || null,
      department_id: form.department_id || null,
      phone: form.phone || null,
      mobile: form.mobile || null,
      gender: form.gender || null,
      user_type: form.user_type || 'internal',
      company: form.company || null,
      contact_person: form.contact_person || null,
      notes: form.notes || null,
    }
    if (!isEdit.value) {
      payload.username = form.username
      payload.password = form.password
    }
    if (isEdit.value) {
      await updateUser(editId.value, payload)
      ElMessage.success('用户已更新')
    } else {
      await createUser(payload)
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    page.value = 1
    await fetchList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

function generatePasswordValue() {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const lower = 'abcdefghjkmnpqrstuvwxyz'
  const digits = '23456789'
  const symbols = '!@#$%&*_+-='
  const all = upper + lower + digits + symbols

  while (true) {
    const chars = [
      upper[Math.floor(Math.random() * upper.length)],
      lower[Math.floor(Math.random() * lower.length)],
      digits[Math.floor(Math.random() * digits.length)],
      symbols[Math.floor(Math.random() * symbols.length)],
    ]
    for (let i = 0; i < 6; i++) {
      chars.push(all[Math.floor(Math.random() * all.length)])
    }
    for (let i = chars.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[chars[i], chars[j]] = [chars[j], chars[i]]
    }
    const pwd = chars.join('')
    let hasConsecutive = false
    for (let i = 0; i < pwd.length - 2; i++) {
      if (pwd.charCodeAt(i + 1) - pwd.charCodeAt(i) === 1 && pwd.charCodeAt(i + 2) - pwd.charCodeAt(i + 1) === 1) {
        hasConsecutive = true
        break
      }
    }
    if (!hasConsecutive) return pwd
  }
}

function generatePassword() {
  form.password = generatePasswordValue()
}

async function handleToggleActive(row) {
  const action = row.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(`确定${action}用户「${row.username}」吗？`, `${action}确认`, {
      type: 'warning',
      confirmButtonText: `确定${action}`,
      cancelButtonText: '取消',
    })
    await updateUser(row.id, { is_active: !row.is_active })
    ElMessage.success(`用户已${action}`)
    await fetchList()
  } catch { /* 取消 */ }
}

const selectedIds = ref([])
function onSelect(val) { selectedIds.value = val.map(v => v.id) }

async function handleBatchDelete() {
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个用户吗？`, '批量删除', { type: 'error' })
  } catch { return }
  try {
    const res = await batchDeleteUsers(selectedIds.value)
    ElMessage.success(res.message)
    selectedIds.value = []
    page.value = 1
    await fetchList()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '删除失败') }
}

async function handleBatchDisable() {
  try {
    await ElMessageBox.confirm(`确定禁用选中的 ${selectedIds.value.length} 个用户吗？`, '批量禁用', { type: 'warning' })
  } catch { return }
  try {
    const res = await batchDisableUsers(selectedIds.value, 'disable')
    ElMessage.success(res.message)
    selectedIds.value = []
    await fetchList()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '操作失败') }
}

async function handleBatchEnable() {
  try {
    const res = await batchDisableUsers(selectedIds.value, 'enable')
    ElMessage.success(res.message)
    selectedIds.value = []
    await fetchList()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '操作失败') }
}

const deleting = ref(false)

async function handleDelete(row) {
  if (deleting.value) return
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.username}」吗？此操作不可恢复。`, '删除确认', {
      type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消',
    })
  } catch { return }
  deleting.value = true
  try {
    await deleteUser(row.id)
    ElMessage.success('用户已删除')
    page.value = 1
    await fetchList()
  } catch (e) {
    ElMessage.error('删除失败：' + (e?.response?.data?.detail || e?.message || '未知错误'))
  } finally {
    deleting.value = false
  }
}

function openResetPassword(row) {
  passwordTarget.value = row
  passwordForm.new_password = ''
  passwordDialogVisible.value = true
}

async function handleResetPassword() {
  if (!passwordForm.new_password || passwordForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  resetting.value = true
  try {
    await resetUserPassword(passwordTarget.value.id, passwordForm.new_password)
    ElMessage.success('密码已重置')
    passwordDialogVisible.value = false
  } catch (e) {
    ElMessage.error('重置失败')
  } finally {
    resetting.value = false
  }
}

onMounted(() => {
  fetchList()
  loadDeptOptions()
})
</script>

<style scoped>
.account-page {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.filter-bar {
  margin-bottom: 14px;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
.lookup-result {
  margin-bottom: 8px;
}
.lookup-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
.staff-radio-group {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.staff-radio {
  padding: 10px 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  width: 100%;
  margin: 0;
}
.staff-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.staff-meta {
  color: #909399;
  font-size: 12px;
}
</style>
