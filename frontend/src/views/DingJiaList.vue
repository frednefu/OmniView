<template>
  <div class="page">
    <div class="page-header">
      <h2>鼎甲备份管理</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
        <el-dropdown trigger="click">
          <el-button type="warning" plain>批量操作<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleScanAll"><el-icon><Refresh /></el-icon>全部扫描</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon>添加设备</el-button>
      </div>
    </div>

    <el-card>
      <el-table :data="items" stripe v-loading="loading">
        <template #empty><el-empty description="暂无设备" :image-size="80"/></template>
        <el-table-column prop="id" label="ID" width="60"/>
        <el-table-column prop="name" label="名称" min-width="120"/>
        <el-table-column prop="host" label="服务器" width="160"/>
        <el-table-column prop="api_key_masked" label="API Key" width="130"/>
        <el-table-column prop="access_key_masked" label="Access Key" width="130"/>
        <el-table-column label="扫描间隔" width="100">
          <template #default="{row}">{{ row.scan_interval > 0 ? row.scan_interval + 's' : '手动' }}</template>
        </el-table-column>
        <el-table-column label="最后扫描" width="150">
          <template #default="{row}">
            <div style="display:flex;align-items:center;gap:6px">
              <el-tag v-if="row.last_scan_status==='success'" type="success" size="small">成功</el-tag>
              <el-tag v-else-if="row.last_scan_status==='failed'" type="danger" size="small">失败</el-tag>
              <span v-else style="color:#c0c4cc">未扫描</span>
              <span v-if="row.last_scan_duration" style="color:#909399;font-size:12px">{{row.last_scan_duration}}s</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{row}"><el-tag :type="row.is_active?'success':'info'" size="small">{{row.is_active?'启用':'禁用'}}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{row}">
            <el-button size="small" @click="$router.push(`/dingjia/${row.id}`)">详情</el-button>
            <el-dropdown v-if="authStore.isAdmin" trigger="click" @command="(cmd)=>handleCommand(cmd,row)">
              <el-button size="small">更多<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="scan"><el-icon><Refresh /></el-icon>扫描</el-dropdown-item>
                  <el-dropdown-item command="edit"><el-icon><Edit /></el-icon>编辑</el-dropdown-item>
                  <el-dropdown-item command="delete" divided><span style="color:#f56c6c"><el-icon><Delete /></el-icon>删除</span></el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dlg" :title="isEdit?'编辑设备':'添加设备'" width="500px" @closed="resetForm">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name"/></el-form-item>
        <el-form-item label="服务器 IP"><el-input v-model="form.host"/></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" :placeholder="isEdit?'留空保持原值':''" show-password type="password"/></el-form-item>
        <el-form-item label="Access Key"><el-input v-model="form.access_key" :placeholder="isEdit?'留空保持原值':''" show-password type="password"/></el-form-item>
        <el-form-item label="扫描周期(秒)"><el-input-number v-model="form.scan_interval" :min="60"/></el-form-item>
        <el-form-item><el-button @click="handleTest">测试连接</el-button><el-button type="primary" @click="handleSave">保存</el-button></el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Edit, Delete, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'

const authStore=useAuthStore()
const items=ref([]),loading=ref(false)
const dlg=ref(false),isEdit=ref(false),editId=ref(null)
const form=reactive({name:'',host:'',api_key:'',access_key:'',scan_interval:86400})

function resetForm(){Object.assign(form,{name:'',host:'',api_key:'',access_key:'',scan_interval:86400})}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
async function openEdit(r){
  editId.value=r.id;isEdit.value=true
  Object.assign(form,{name:r.name,host:r.host,api_key:'',access_key:'',scan_interval:r.scan_interval})
  dlg.value=true
  try{const res=await api.get(`/dingjia/${r.id}`);form.api_key=res.data.api_key;form.access_key=res.data.access_key}catch{}
}

async function handleCommand(cmd,row){
  if(cmd==='scan') await handleScan(row)
  else if(cmd==='edit') openEdit(row)
  else if(cmd==='delete') await handleDelete(row)
}

async function fetchList(){loading.value=true;try{const r=await api.get('/dingjia');items.value=r.data.items}catch{}finally{loading.value=false}}
async function handleTest(){try{const r=await api.post('/dingjia/test',{host:form.host,api_key:form.api_key,access_key:form.access_key});ElMessage[r.data.success?'success':'error'](r.data.message)}catch{ElMessage.error('测试失败')}}
async function handleSave(){
  const data={...form}
  try{
    if(isEdit.value){await api.put(`/dingjia/${editId.value}`,data);ElMessage.success('已更新')}
    else{await api.post('/dingjia',data);ElMessage.success('已创建')}
    dlg.value=false;fetchList()
  }catch{ElMessage.error('保存失败')}
}
async function handleScan(r){try{const res=await api.post(`/dingjia/${r.id}/scan`);ElMessage.success(res.data.message);fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'扫描失败')}}
async function handleDelete(r){try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'});await api.delete(`/dingjia/${r.id}`);ElMessage.success('已删除');fetchList()}catch{}}
async function handleScanAll(){for(const r of items.value){if(r.is_active) try{await api.post(`/dingjia/${r.id}/scan`)}catch{}};ElMessage.success('全部扫描已触发');fetchList()}
onMounted(fetchList)
</script>

<style scoped>
.page{padding:20px}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.page-header h2{margin:0;font-size:20px}.header-actions{display:flex;gap:8px}
</style>
