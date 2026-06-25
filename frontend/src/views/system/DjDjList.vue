<template>
  <div class="page">
    <div class="page-header">
      <h2>等保信息维护</h2>
      <div class="header-actions">
        <template v-if="authStore.isAdmin">
          <el-button @click="triggerImport">导入Excel</el-button>
          <input ref="fileInput" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
          <el-button type="primary" @click="handleExport">导出Excel</el-button>
        </template>
        <el-button type="success" @click="openCreate">添加记录</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索系统名称/备案编号" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList" /></template>
      </el-input>
      <el-button v-if="authStore.isAdmin && selectedIds.length>0" type="danger" @click="handleBatchDelete">批量删除 ({{selectedIds.length}})</el-button>
      <span style="color:#909399;font-size:13px;line-height:32px">共 {{total}} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" @selection-change="onSelect">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="record_no" label="备案编号" width="200" />
      <el-table-column prop="system_name" label="系统名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="org_name" label="备案单位" min-width="160" />
      <el-table-column prop="eval_org" label="测评单位" min-width="160" />
      <el-table-column prop="level" label="等级" width="80" />
      <el-table-column prop="record_date" label="备案日期" width="120" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{row}">
          <template v-if="authStore.isAdmin || row.created_by === authStore.user?.id">
            <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" size="small" @click="openEdit(row)"/></el-tooltip>
            <el-tooltip content="删除"><el-button link type="danger" :icon="Delete" size="small" @click="handleDelete(row)"/></el-tooltip>
          </template>
          <template v-else-if="!row.claimed_by">
            <el-tooltip content="认领"><el-button link type="success" size="small" @click="handleClaim(row,'djdj')">认领</el-button></el-tooltip>
          </template>
          <template v-else-if="row.claimed_by === authStore.user?.id">
            <el-tooltip content="撤销认领"><el-button link type="warning" size="small" @click="handleRevoke(row,'djdj')">撤销</el-button></el-tooltip>
          </template>
          <span v-else style="color:#c0c4cc;font-size:12px">-</span>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <el-dialog v-model="dlg" :title="isEdit?'编辑':'添加'" width="550px">
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="备案编号"><el-input v-model="form.record_no"/></el-form-item>
        <el-form-item label="系统名称"><el-input v-model="form.system_name"/></el-form-item>
        <el-form-item label="备案单位"><el-input v-model="form.org_name"/></el-form-item>
        <el-form-item label="测评单位"><el-input v-model="form.eval_org" placeholder="等保测评机构名称"/></el-form-item>
        <el-form-item label="等级">
          <el-select v-model="form.level"><el-option v-for="l in ['一级','二级','三级','四级']" :key="l" :label="l" :value="l"/></el-select>
        </el-form-item>
        <el-form-item label="备案日期"><el-input v-model="form.record_date" type="date"/></el-form-item>
        <el-form-item label="备案证明" v-if="isEdit">
          <input type="file" accept="image/*" @change="onImageUpload"/>
          <div v-if="editId && form.image_path" style="margin-top:6px;display:flex;align-items:flex-start;gap:4px">
            <img :src="'/api/info-systems/djdj/image/'+editId" style="max-width:200px;max-height:150px;cursor:pointer;border:1px solid #eee" @click="previewVisible=true" @error="e=>{e.target.style.display='none';form.image_path=''}"/>
            <el-button link type="danger" :icon="Close" size="small" @click="handleDeleteImage"/>
          </div>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2"/></el-form-item>
      </el-form>
      <template #footer><el-button @click="dlg=false">取消</el-button><el-button type="primary" @click="handleSave">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="备案证明" width="80%" :close-on-click-modal="true">
      <img :src="'/api/info-systems/djdj/image/'+editId" style="max-width:100%" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Close, Edit, Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'

const authStore=useAuthStore()
const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref('')
const selectedIds=ref([]),dlg=ref(false),isEdit=ref(false),editId=ref(null),fileInput=ref(null),previewVisible=ref(false)
const form=reactive({record_no:'',system_name:'',org_name:'',eval_org:'',level:'',record_date:'',remark:'',image_path:''})

function resetForm(){Object.assign(form,{record_no:'',system_name:'',org_name:'',eval_org:'',level:'',record_date:'',remark:'',image_path:''})}
function onSelect(v){selectedIds.value=v.map(r=>r.id)}
async function fetchList(){loading.value=true;try{const r=await api.get('/info-systems/djdj',{params:{page:page.value,size:size.value,search:search.value}});items.value=r.data.items;total.value=r.data.total}catch{}finally{loading.value=false}}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
function openEdit(r){editId.value=r.id;isEdit.value=true;Object.keys(form).forEach(k=>{if(r[k]!==undefined)form[k]=r[k]||''});form.image_path=r.image_path||null;form.eval_org=r.eval_org||r.dept_name||'';dlg.value=true}
async function handleSave(){
  try{
    const data={...form}
    if(!data.image_path) delete data.image_path
    if(isEdit.value){await api.put('/info-systems/djdj/'+editId.value,data);ElMessage.success('已更新')}
    else{await api.post('/info-systems/djdj',data);ElMessage.success('已创建')}
    dlg.value=false;fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'保存失败')}
}
async function handleDelete(r){
  try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'})}catch{return}
  try{await api.delete('/info-systems/djdj/'+r.id);ElMessage.success('已删除');fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'删除失败，可能是权限不足')}
}
async function handleBatchDelete(){
  try{await ElMessageBox.confirm('确定删除选中记录?','批量删除',{type:'error'})}catch{return}
  try{await api.post('/info-systems/djdj/batch-delete',{ids:selectedIds.value});ElMessage.success('已删除');selectedIds.value=[];fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'批量删除失败，需要管理员权限')}
}
function triggerImport(){fileInput.value?.click()}
async function onFileChange(e){const file=e.target.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);try{const r=await api.post('/info-systems/djdj/import',fd);const dupes=r.data.duplicates;if(dupes&&dupes.length>0){let msg=dupes.map(d=>`${d['备案编号']}: ${d['导入系统名']} ⇄ ${d['已存在系统名']}`).join('<br>');ElMessageBox.alert(msg,'重复数据('+dupes.length+'条)',{dangerouslyUseHTMLString:true,confirmButtonText:'知道了'})}ElMessage.success(r.data.message);fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'导入失败')}finally{e.target.value=''}}
async function onImageUpload(e){const file=e.target.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);try{const r=await api.post('/info-systems/djdj/upload-image/'+editId.value,fd);form.image_path=r.data.image_path;ElMessage.success('已上传')}catch{ElMessage.error('上传失败')}}
async function handleDeleteImage(){try{await api.delete('/info-systems/djdj/delete-image/'+editId.value);form.image_path='';ElMessage.success('已删除')}catch{ElMessage.error('删除失败')}}
async function handleExport(){try{const r=await api.get('/info-systems/djdj/export',{responseType:'blob'});const url=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=url;a.download='djdj_export.xlsx';a.click();URL.revokeObjectURL(url)}catch{}}
onMounted(()=>{fetchList()})
</script>
<style scoped>.page{padding:20px}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.page-header h2{margin:0;font-size:20px}.header-actions{display:flex;gap:8px}.filter-bar{margin-bottom:14px;display:flex;gap:10px;align-items:center}</style>
