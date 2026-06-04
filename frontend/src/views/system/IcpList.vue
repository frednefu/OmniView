<template>
  <div class="page">
    <div class="page-header">
      <h2>ICP备案信息维护</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
        <el-button @click="triggerImport">导入Excel</el-button>
        <input ref="fileInput" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
        <el-button type="primary" @click="handleExport">导出Excel</el-button>
        <el-button type="success" @click="openCreate">添加记录</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索备案编号/主体" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList" /></template>
      </el-input>
      <span style="color:#909399;font-size:13px;line-height:32px">共 {{total}} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" :default-sort="{prop:'id',order:'descending'}">
      <el-table-column prop="icp_no" label="ICP备案编号" width="200" sortable />
      <el-table-column prop="org_name" label="备案主体" min-width="160" sortable />
      <el-table-column prop="domain" label="备案域名" min-width="200" show-overflow-tooltip sortable />
      <el-table-column prop="record_date" label="备案日期" width="120" sortable />
      <el-table-column label="操作" width="100" fixed="right" v-if="authStore.isAdmin">
        <template #default="{row}">
          <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" size="small" @click="openEdit(row)"/></el-tooltip>
          <el-tooltip content="删除"><el-button link type="danger" :icon="Delete" size="small" @click="handleDelete(row)"/></el-tooltip>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px" />

    <el-dialog v-model="dlg" :title="isEdit ? '编辑' : '添加'" width="500px">
      <el-form :model="form" label-width="100px" size="small">
        <el-form-item label="备案编号"><el-input v-model="form.icp_no" /></el-form-item>
        <el-form-item label="备案主体"><el-input v-model="form.org_name" /></el-form-item>
        <el-form-item label="备案域名"><el-input v-model="form.domain" /></el-form-item>
        <el-form-item label="备案日期"><el-input v-model="form.record_date" type="date" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg=false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Edit, Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'

const authStore = useAuthStore()
const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')
const dlg = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const fileInput = ref(null)
const form = reactive({ icp_no: '', org_name: '', domain: '', record_date: '', remark: '' })

function resetForm() { Object.assign(form, { icp_no: '', org_name: '', domain: '', record_date: '', remark: '' }) }
async function fetchList() { loading.value = true; try { const r = await api.get('/info-systems/icp', { params: { page: page.value, size: size.value, search: search.value } }); items.value = r.data.items; total.value = r.data.total } catch { } finally { loading.value = false } }
function openCreate() { resetForm(); isEdit.value = false; dlg.value = true }
function openEdit(r) { editId.value = r.id; isEdit.value = true; Object.keys(form).forEach(k => { if (r[k] !== undefined) form[k] = r[k] }); dlg.value = true }
async function handleSave() { try { if (isEdit.value) { await api.put('/info-systems/icp/' + editId.value, form); ElMessage.success('已更新') } else { await api.post('/info-systems/icp', form); ElMessage.success('已创建') } dlg.value = false; fetchList() } catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败') } }
async function handleDelete(r) { try { await ElMessageBox.confirm('确定删除?', '确认', { type: 'warning' }); await api.delete('/info-systems/icp/' + r.id); ElMessage.success('已删除'); fetchList() } catch { } }
function triggerImport() { fileInput.value?.click() }
async function onFileChange(e) { const file = e.target.files[0]; if (!file) return; const fd = new FormData(); fd.append('file', file); try { const r = await api.post('/info-systems/icp/import', fd); ElMessage.success(r.data.message); fetchList() } catch { ElMessage.error('导入失败') } finally { e.target.value = '' } }
async function handleExport() { try { const r = await api.get('/info-systems/icp/export', { responseType: 'blob' }); const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = 'icp_export.xlsx'; a.click(); URL.revokeObjectURL(url) } catch { } }
onMounted(fetchList)
</script>

<style scoped>
.page { padding: 20px }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px }
.page-header h2 { margin: 0; font-size: 20px }
.header-actions { display: flex; gap: 8px }
.filter-bar { margin-bottom: 14px; display: flex; gap: 8px }
</style>
