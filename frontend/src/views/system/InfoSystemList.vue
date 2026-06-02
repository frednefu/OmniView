<template>
  <div class="page">
    <div class="page-header">
      <h2>信息系统维护</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
        <el-upload :before-upload="handleImport" accept=".xlsx" :show-file-list="false">
          <el-button>导入Excel</el-button>
        </el-upload>
        <el-button type="primary" @click="handleExport">导出Excel</el-button>
        <el-button type="success" @click="openCreate">添加系统</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索名称/IP/域名" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <el-select v-model="fillTypeFilter" placeholder="填报类型" clearable style="width:120px" @change="fetchList">
        <el-option label="导入" value="导入"/><el-option label="手动" value="手动"/><el-option label="自动" value="自动"/>
      </el-select>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small">
      <el-table-column prop="asset_id" label="资产ID" width="180" show-overflow-tooltip/>
      <el-table-column prop="system_name" label="系统名称" min-width="160" show-overflow-tooltip/>
      <el-table-column prop="system_type" label="类型" width="120"/>
      <el-table-column prop="ip_address" label="IP" width="140"/>
      <el-table-column prop="domain" label="域名" min-width="160" show-overflow-tooltip/>
      <el-table-column prop="fill_type" label="填报" width="70">
        <template #default="{row}"><el-tag :type="row.fill_type==='导入'?'':'success'" size="small">{{row.fill_type}}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{row}">
          <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>size" v-model:current-page="page" :page-size="size" :total="total" layout="prev,pager,next" @current-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <el-dialog v-model="dlg" :title="isEdit?'编辑':'添加'" width="700px" @closed="resetForm">
      <el-form :model="form" label-width="100px" size="small">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="资产ID"><el-input v-model="form.asset_id" placeholder="自动生成"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="系统名称"><el-input v-model="form.system_name"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="资产类型"><el-input v-model="form.system_type"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="信息系统类型"><el-input v-model="form.sub_type"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="IP地址"><el-input v-model="form.ip_address"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="域名/URL"><el-input v-model="form.domain"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="单位名称"><el-input v-model="form.org_name"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="运维单位"><el-input v-model="form.dept_name"/></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="联系人"><el-input v-model="form.contact"/></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="电话"><el-input v-model="form.contact_phone"/></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="填报类型">
            <el-select v-model="form.fill_type"><el-option v-for="t in ['导入','手动','自动']" :key="t" :label="t" :value="t"/></el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="等保编号"><el-input v-model="form.djdj_no"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="等保等级"><el-input v-model="form.djdj_level"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="等保日期"><el-date-picker v-model="form.djdj_date" type="date" value-format="YYYY-MM-DD" style="width:100%"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="ICP编号"><el-input v-model="form.icp_no"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="ICP日期"><el-date-picker v-model="form.icp_date" type="date" value-format="YYYY-MM-DD" style="width:100%"/></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2"/></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="dlg=false">取消</el-button><el-button type="primary" @click="handleSave">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'
const authStore=useAuthStore()
const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref(''),fillTypeFilter=ref('')
const dlg=ref(false),isEdit=ref(false),editId=ref(null)
const form=reactive({asset_id:'',system_name:'',system_type:'',sub_type:'',ip_address:'',domain:'',org_name:'',dept_name:'',contact:'',contact_phone:'',fill_type:'手动',djdj_no:'',djdj_level:'',djdj_date:null,icp_no:'',icp_date:null,remark:''})
function resetForm(){Object.assign(form,{asset_id:'',system_name:'',system_type:'',sub_type:'',ip_address:'',domain:'',org_name:'',dept_name:'',contact:'',contact_phone:'',fill_type:'手动',djdj_no:'',djdj_level:'',djdj_date:null,icp_no:'',icp_date:null,remark:''})}
async function fetchList(){loading.value=true;try{const r=await api.get('/info-systems',{params:{page:page.value,size:size.value,search:search.value,fill_type:fillTypeFilter.value}});items.value=r.data.items;total.value=r.data.total}catch{}finally{loading.value=false}}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
function openEdit(r){editId.value=r.id;isEdit.value=true;Object.keys(form).forEach(k=>{if(r[k]!==undefined)form[k]=r[k]});dlg.value=true}
async function handleSave(){try{if(isEdit.value){await api.put(`/info-systems/${editId.value}`,form);ElMessage.success('已更新')}else{await api.post('/info-systems',form);ElMessage.success('已创建')}dlg.value=false;fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'保存失败')}}
async function handleDelete(r){try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'});await api.delete(`/info-systems/${r.id}`);ElMessage.success('已删除');fetchList()}catch{}}
async function handleImport(file){const fd=new FormData();fd.append('file',file);try{const r=await api.post('/info-systems/import',fd);ElMessage.success(r.data.message);fetchList()}catch{ElMessage.error('导入失败')}return false}
async function handleExport(){try{const r=await api.get('/info-systems/export',{responseType:'blob'});const url=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=url;a.download='info_systems.xlsx';a.click();URL.revokeObjectURL(url)}catch{}}
onMounted(fetchList)
</script>
<style scoped>.page{padding:20px}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.page-header h2{margin:0;font-size:20px}.header-actions{display:flex;gap:8px}.filter-bar{margin-bottom:14px;display:flex;gap:8px}</style>
