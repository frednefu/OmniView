<template>
  <div class="page">
    <div class="page-header">
      <h2>外链管理</h2>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索标题或token" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <span style="color:#909399;font-size:13px;line-height:32px">共 {{ total }} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small">
      <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
      <el-table-column label="链接" min-width="280" show-overflow-tooltip>
        <template #default="{row}">{{ origin }}{{ row.url }}</template>
      </el-table-column>
      <el-table-column label="密码" width="80">
        <template #default="{row}">{{ row.has_password ? '有' : '无' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{row}">
          <el-tag :type="row.is_active?'success':'danger'" size="small">{{ row.is_active?'有效':'已关闭' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="access_count" label="访问" width="60" />
      <el-table-column label="过期时间" width="160">
        <template #default="{row}">{{ row.expire_at ? new Date(row.expire_at).toLocaleString('zh-CN') : '永不过期' }}</template>
      </el-table-column>
      <el-table-column prop="created_by_name" label="创建人" width="80" />
      <el-table-column label="操作" width="180">
        <template #default="{row}">
          <el-button link type="primary" size="small" @click="copyLink(row)">复制链接</el-button>
          <el-button link size="small" :type="row.is_active?'warning':'success'" @click="toggleLink(row)">{{ row.is_active?'禁用':'启用' }}</el-button>
          <el-button link type="danger" size="small" @click="deleteLink(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import api from '@/api/index'

const items = ref([]), loading = ref(false), page = ref(1), size = ref(20), total = ref(0), search = ref('')
const origin = window.location.origin

async function fetchList() {
  loading.value = true
  try {
    const r = await api.get('/shared-links', { params: { page: page.value, size: size.value, search: search.value } })
    items.value = r.data.items; total.value = r.data.total
  } catch { } finally { loading.value = false }
}

function copyLink(row) {
  const url = origin + row.url
  navigator.clipboard.writeText(url).then(() => ElMessage.success('已复制'))
    .catch(() => ElMessage.warning('复制失败，请手动复制'))
}

async function toggleLink(row) {
  try {
    const r = await api.put(`/shared-links/${row.token}/toggle`)
    ElMessage.success(r.data.message); fetchList()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function deleteLink(row) {
  try {
    await ElMessageBox.confirm('确定删除此外链？', '确认', { type: 'warning' })
    await api.delete(`/shared-links/${row.token}`)
    ElMessage.success('已删除'); fetchList()
  } catch { /* */ }
}

onMounted(fetchList)
</script>
<style scoped>
.page { padding: 20px }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px }
.page-header h2 { margin: 0; font-size: 20px }
.filter-bar { margin-bottom: 14px; display: flex; gap: 8px; align-items: center }
</style>
