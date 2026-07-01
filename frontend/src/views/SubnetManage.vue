<template>
  <div class="page">
    <div class="page-header">
      <h2>地址段管理</h2>
      <div style="display:flex;gap:8px">
        <el-button v-if="!authStore.isAdmin" @click="openSubDialog">订阅管理</el-button>
        <el-button type="primary" @click="openDialog()"><el-icon><Plus /></el-icon>添加地址段</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索名称/CIDR/网关" clearable style="width:220px" @keyup.enter="fetchSubnets" @clear="fetchSubnets">
        <template #append><el-button :icon="Search" @click="fetchSubnets"/></template>
      </el-input>
      <el-select v-if="authStore.isAdmin" v-model="filterUser" placeholder="维护账号" clearable style="width:120px" @change="fetchSubnets">
        <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id"/>
      </el-select>
      <span style="color:#909399;font-size:13px;line-height:32px;white-space:nowrap">共 {{ total }} 条</span>
    </div>
    <el-table :data="subnets" v-loading="loading" stripe size="small" @sort-change="onSort" :default-sort="{prop:'id',order:'descending'}">
      <el-table-column prop="name" label="名称" min-width="120" sortable="custom" />
      <el-table-column prop="subnet_cidr" label="CIDR" min-width="160" sortable="custom" />
      <el-table-column prop="gateway" label="网关" min-width="130" sortable="custom" />
      <el-table-column prop="vlan_id" label="VLAN ID" width="90" sortable="custom">
        <template #default="{ row }">{{ row.vlan_id ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
      <el-table-column prop="is_managed" label="管理" width="70" sortable="custom">
        <template #default="{ row }">
          <el-tag :type="row.is_managed ? 'success' : 'info'" size="small">{{ row.is_managed ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_by_name" label="维护账号" width="110">
        <template #default="{ row }">
          <span>{{ row.created_by_name }}</span>
          <el-tag v-if="!authStore.isAdmin && row.created_by !== authStore.user?.id" size="small" type="warning" style="margin-left:4px">订阅</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <template v-if="authStore.isAdmin || row.created_by === authStore.user?.id || row.created_by == null">
            <el-button size="small" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确定删除此地址段？" @confirm="handleDelete(row.id)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
          <template v-else-if="!authStore.isAdmin">
            <el-tooltip :content="row.hidden ? '仪表盘隐藏中，点击展示' : '仪表盘可见，点击隐藏'">
              <el-button size="small" @click="toggleSubShow(row)">
                {{ row.hidden ? '— 隐藏' : '👁 展示' }}
              </el-button>
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchSubnets" @size-change="fetchSubnets" style="justify-content:center;margin-top:16px"/>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑地址段' : '添加地址段'" width="500px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="CIDR" prop="subnet_cidr">
          <el-select v-model="form.subnet_cidr" filterable allow-create clearable default-first-option placeholder="输入或选择 CIDR" style="width:100%" @change="onCidrSelect" @blur="onCidrBlur">
            <el-option v-for="r in routeCidrs" :key="r.cidr" :label="r.cidr" :value="r.cidr" />
          </el-select>
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

    <!-- 订阅管理对话框 -->
    <el-dialog v-model="subVisible" title="订阅管理" width="550px">
      <div style="margin-bottom:12px;display:flex;gap:8px">
        <el-input v-model="subSearch" placeholder="搜索用户姓名或工号" clearable style="flex:1" @keyup.enter="searchSubUser" />
        <el-button type="primary" :loading="subSearching" @click="searchSubUser">搜索</el-button>
      </div>
      <el-table :data="subSearchResults" stripe size="small" max-height="250" v-loading="subSearching">
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="gh" label="工号" width="120" />
        <el-table-column prop="department_name" label="部门" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button v-if="!subMap[row.id]" type="success" size="small" @click="doSubscribe(row)">订阅</el-button>
            <el-button v-else type="danger" size="small" plain @click="doUnsubscribe(row)">取消</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="subList.length > 0" style="margin-top:16px">
        <div style="font-size:13px;color:#606266;margin-bottom:8px">已订阅用户：</div>
        <el-tag v-for="s in subList" :key="s.id" closable style="margin:2px 4px" @close="doUnsubscribe(s)">{{ s.target_name }}</el-tag>
      </div>
      <div v-else style="margin-top:16px;color:#c0c4cc;font-size:13px">暂未订阅任何用户</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useAuthStore } from '@/store/auth'
import { ElMessage } from 'element-plus'
import { Search, Plus } from '@element-plus/icons-vue'
import api from '@/api'

const authStore = useAuthStore()
const subnets = ref([])
const loading = ref(false)
const page = ref(1), size = ref(20), total = ref(0), search = ref('')
const sortField = ref(''), sortOrder = ref('desc')
const filterUser = ref('')
const userOptions = ref([])
const dialogVisible = ref(false), isEdit = ref(false), editId = ref(null), submitting = ref(false)
const formRef = ref(null), routeCidrs = ref([])

const form = reactive({ subnet_cidr: '', name: '', gateway: '', vlan_id: null, description: '', is_managed: true })
const rules = {
  subnet_cidr: [{ required: true, message: '请输入 CIDR', trigger: 'blur' }],
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

function onSort({prop,order}){sortField.value=prop||'';sortOrder.value=order==='ascending'?'asc':'desc';fetchSubnets()}

async function fetchSubnets() {
  loading.value = true
  try {
    const p = { page: page.value, size: size.value, search: search.value }
    if (sortField.value) { p.sort_field = sortField.value; p.sort_order = sortOrder.value }
    if (filterUser.value) p.created_by = filterUser.value
    const { data } = await api.get('/subnets', { params: p })
    subnets.value = data.items; total.value = data.total
  } catch {} finally { loading.value = false }
}
async function loadUsers() {
  try { const { data } = await api.get('/subnets/creators'); userOptions.value = data.items || [] } catch {}
}

async function loadRouteCidrs() {
  try { const { data } = await api.get('/subnets/route-cidrs'); routeCidrs.value = data.items || [] } catch { routeCidrs.value = [] }
}

function onCidrBlur(e) {
  const val = e?.target?.value || ''
  if (val && !routeCidrs.value.find(r => r.cidr === val)) form.subnet_cidr = val
}
function onCidrSelect(val) {
  if (!val) return
  const item = routeCidrs.value.find(r => r.cidr === val)
  if (item) {
    if (item.gateway && item.gateway !== '0.0.0.0' && !form.gateway) form.gateway = item.gateway
    if (item.vlan && !form.vlan_id) { const m = item.vlan.match(/\d+/); if (m) form.vlan_id = parseInt(m[0]) || null }
  }
}

function resetForm() { Object.assign(form, { subnet_cidr: '', name: '', gateway: '', vlan_id: null, description: '', is_managed: true }) }
function openDialog(row) {
  resetForm(); loadRouteCidrs()
  if (row) { isEdit.value = true; editId.value = row.id; Object.assign(form, { subnet_cidr: row.subnet_cidr, name: row.name, gateway: row.gateway, vlan_id: row.vlan_id, description: row.description, is_managed: row.is_managed }) }
  else { isEdit.value = false; editId.value = null }
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (isEdit.value) { await api.put(`/subnets/${editId.value}`, { ...form }); ElMessage.success('已更新') }
    else { await api.post('/subnets', { ...form }); ElMessage.success('已创建') }
    dialogVisible.value = false; fetchSubnets()
  } catch {} finally { submitting.value = false }
}

async function handleDelete(id) {
  try { await api.delete(`/subnets/${id}`); ElMessage.success('已删除'); fetchSubnets() } catch {}
}

// ── 订阅管理 ──
const subVisible = ref(false), subSearch = ref(''), subSearching = ref(false)
const subSearchResults = ref([]), subList = ref([]), subMap = ref({})

async function openSubDialog() {
  subVisible.value = true; subSearch.value = ''; subSearchResults.value = []
  await loadSubscriptions()
}
async function loadSubscriptions() {
  try {
    const { data } = await api.get('/subnets/subscriptions')
    subList.value = data.items || []
    subMap.value = {}
    subList.value.forEach(s => { subMap.value[s.target_user_id] = true })
  } catch { subList.value = []; subMap.value = {} }
}
async function searchSubUser() {
  const q = subSearch.value.trim()
  if (!q) return
  subSearching.value = true
  try {
    const { data } = await api.get('/info-systems/staff-search', { params: { q } })
    subSearchResults.value = (data.items || []).filter(u => u.id !== authStore.user?.id)
  } catch { subSearchResults.value = [] } finally { subSearching.value = false }
}
async function doSubscribe(row) {
  try {
    await api.post(`/subnets/subscribe/${row.id}`)
    ElMessage.success(`已订阅 ${row.name}`)
    subMap.value[row.id] = true
    subList.value.push({ id: Date.now(), target_user_id: row.id, target_name: row.name })
    fetchSubnets()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '订阅失败') }
}
async function doUnsubscribe(row) {
  try {
    await api.delete(`/subnets/subscribe/${row.target_user_id || row.id}`)
    ElMessage.success('已取消订阅')
    const uid = row.target_user_id || row.id
    delete subMap.value[uid]
    subList.value = subList.value.filter(s => s.target_user_id !== uid)
    fetchSubnets()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '取消失败') }
}
async function toggleSubShow(row) {
  try {
    const { data } = await api.put(`/subnets/hidden/${row.id}`)
    row.hidden = data.hidden
    ElMessage.success(data.hidden ? '已在仪表盘隐藏' : '已在仪表盘展示')
  } catch { /* ignore */ }
}

onMounted(()=>{fetchSubnets();if(authStore.isAdmin)loadUsers()})
</script>
<style scoped>
.page{padding:20px}
.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.page-header h2{margin:0;font-size:20px}
.filter-bar{margin-bottom:14px;display:flex;gap:8px;align-items:center}
</style>
