<template>
  <div class="page">
    <div class="page-header">
      <h2>操作日志</h2>
      <div class="header-actions">
        <el-button type="danger" plain @click="showCleanDlg = true">清理日志</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索用户/路径/描述" clearable style="width:220px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <el-select v-model="filterMethod" placeholder="请求方式" clearable style="width:100px" @change="fetchList">
        <el-option v-for="m in ['GET','POST','PUT','DELETE']" :key="m" :label="m" :value="m"/>
      </el-select>
      <el-select v-model="filterStatus" placeholder="执行结果" clearable style="width:110px" @change="fetchList">
        <el-option label="成功" value="success"/><el-option label="失败" value="failed"/>
      </el-select>
      <span style="color:#909399;font-size:13px;line-height:32px;white-space:nowrap">共 {{ total }} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" @sort-change="onSort" :default-sort="{prop:'created_at',order:'descending'}">
      <el-table-column prop="username" label="用户" width="100" sortable="custom" />
      <el-table-column prop="ip_address" label="IP地址" width="140" sortable="custom" />
      <el-table-column prop="method" label="方式" width="70" sortable="custom">
        <template #default="{row}"><el-tag :type="methodTag(row.method)" size="small">{{ row.method }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="api_path" label="操作路径" min-width="200" show-overflow-tooltip sortable="custom" />
      <el-table-column prop="detail" label="操作描述" min-width="140" show-overflow-tooltip />
      <el-table-column prop="status_code" label="状态码" width="80" sortable="custom">
        <template #default="{row}">
          <el-tag :type="row.status_code<400?'success':'danger'" size="small">{{ row.status_code }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时" width="80" sortable="custom">
        <template #default="{row}">{{ row.duration_ms ? row.duration_ms+'ms' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="操作时间" width="160" sortable="custom">
        <template #default="{row}">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <!-- 清理对话框 -->
    <el-dialog v-model="showCleanDlg" title="清理操作日志" width="400px">
      <el-form label-width="100px">
        <el-form-item label="清理时间">
          <el-select v-model="cleanDays" style="width:200px">
            <el-option label="7天前" :value="7"/><el-option label="15天前" :value="15"/>
            <el-option label="30天前" :value="30"/><el-option label="60天前" :value="60"/>
            <el-option label="90天前" :value="90"/><el-option label="180天前" :value="180"/>
          </el-select>
        </el-form-item>
        <el-form-item label="日志留存">
          <span style="color:#909399">当前保留 {{ cleanDays }} 天前的日志将被清理</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCleanDlg=false">取消</el-button>
        <el-button type="danger" @click="handleClean" :loading="cleaning">确认清理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import api from '@/api/index'

const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref('')
const filterMethod=ref(''),filterStatus=ref('')
const sortField=ref('created_at'),sortOrder=ref('desc')
const showCleanDlg=ref(false),cleanDays=ref(30),cleaning=ref(false)

function formatTime(t){return t?new Date(t).toLocaleString('zh-CN',{hour12:false}):'-'}
function methodTag(m){return {GET:'',POST:'warning',PUT:'primary',DELETE:'danger'}[m]||''}
function onSort({prop,order}){sortField.value=prop||'created_at';sortOrder.value=order==='ascending'?'asc':'desc';page.value=1;fetchList()}

async function fetchList(){
  loading.value=true
  try{
    const r=await api.get('/operation-logs',{params:{page:page.value,size:size.value,search:search.value,method:filterMethod.value,status:filterStatus.value,sort_field:sortField.value,sort_order:sortOrder.value}})
    items.value=r.data.items;total.value=r.data.total
  }catch{}finally{loading.value=false}
}

async function handleClean(){
  cleaning.value=true
  try{
    const r=await api.delete('/operation-logs',{params:{before_days:cleanDays.value}})
    ElMessage.success(r.data.message);showCleanDlg.value=false;fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'清理失败')}finally{cleaning.value=false}
}

onMounted(fetchList)
</script>
<style scoped>.page{padding:20px}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.page-header h2{margin:0;font-size:20px}.header-actions{display:flex;gap:8px}.filter-bar{margin-bottom:14px;display:flex;gap:8px;align-items:center}</style>
