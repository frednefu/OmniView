<template>
  <div class="page">
    <div class="page-header">
      <h2>供应链信息维护</h2>
      <el-button type="success" @click="openCreate" v-if="authStore.isAdmin">添加单位</el-button>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索单位名称" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <span style="color:#909399;font-size:13px;line-height:32px">共 {{total}} 条</span>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small">
      <el-table-column prop="company_name" label="单位名称" min-width="180" show-overflow-tooltip/>
      <el-table-column prop="credit_code" label="信用代码" width="180"/>
      <el-table-column prop="company_type" label="类型" width="100"/>
      <el-table-column prop="importance" label="重要程度" width="80"/>
      <el-table-column prop="security_contact" label="联系人" width="80"/>
      <el-table-column prop="security_phone" label="电话" width="120"/>
      <el-table-column label="操作" width="120" fixed="right" v-if="authStore.isAdmin">
        <template #default="{row}"><el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button><el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button></template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>size" v-model:current-page="page" :page-size="size" :total="total" layout="prev,pager,next" @current-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <el-dialog v-model="dlg" :title="isEdit?'编辑':'添加'" width="700px">
      <el-form :model="form" label-width="140px" size="small">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="单位名称"><el-input v-model="form.company_name"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="信用代码"><el-input v-model="form.credit_code"/></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="注册地址"><el-input v-model="form.address"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="类型">
            <el-select v-model="form.company_type"><el-option v-for="t in companyTypes" :key="t" :label="t" :value="t"/></el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="境外资本">
            <el-select v-model="form.has_foreign_capital"><el-option label="是" value="是"/><el-option label="否" value="否"/></el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="安全责任部门"><el-input v-model="form.security_dept"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系人"><el-input v-model="form.security_contact"/></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="手机"><el-input v-model="form.security_phone"/></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="服务行业">
            <div style="max-height:120px;overflow-y:auto;border:1px solid #dcdfe6;border-radius:4px;padding:8px">
              <el-checkbox-group v-model="form.industryArr" @change="form.industry=form.industryArr.join(',')">
                <el-checkbox v-for="t in industries" :key="t" :label="t" :value="t" style="margin-right:12px;margin-bottom:4px"/></el-checkbox-group>
            </div>
          </el-form-item></el-col>
          <el-col :span="24"><el-form-item label="服务类型">
            <div style="max-height:100px;overflow-y:auto;border:1px solid #dcdfe6;border-radius:4px;padding:8px">
              <el-checkbox-group v-model="form.serviceTypeArr" @change="form.service_type=form.serviceTypeArr.join(',')">
                <el-checkbox v-for="t in serviceTypes" :key="t" :label="t" :value="t" style="margin-right:12px;margin-bottom:4px"/></el-checkbox-group>
            </div>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="重要程度">
            <el-select v-model="form.importance"><el-option v-for="t in importances" :key="t" :label="t" :value="t"/></el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="数据最高级别">
            <el-select v-model="form.data_level"><el-option v-for="t in dataLevels" :key="t" :label="t" :value="t"/></el-select>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="存储位置">
            <div style="max-height:100px;overflow-y:auto;border:1px solid #dcdfe6;border-radius:4px;padding:8px">
              <el-checkbox-group v-model="form.dataLocationArr" @change="form.data_location=form.dataLocationArr.join(',')">
                <el-checkbox v-for="t in dataLocations" :key="t" :label="t" :value="t" style="margin-right:12px;margin-bottom:4px"/></el-checkbox-group>
            </div>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="存储方式">
            <div style="max-height:100px;overflow-y:auto;border:1px solid #dcdfe6;border-radius:4px;padding:8px">
              <el-checkbox-group v-model="form.dataStorageArr" @change="form.data_storage=form.dataStorageArr.join(',')">
                <el-checkbox v-for="t in dataStorages" :key="t" :label="t" :value="t" style="margin-right:12px;margin-bottom:4px"/></el-checkbox-group>
            </div>
          </el-form-item></el-col>
          <el-col :span="12"><el-form-item label="数据库类型">
            <div style="max-height:100px;overflow-y:auto;border:1px solid #dcdfe6;border-radius:4px;padding:8px">
              <el-checkbox-group v-model="form.dbTypeArr" @change="form.db_type=form.dbTypeArr.join(',')">
                <el-checkbox v-for="t in dbTypes" :key="t" :label="t" :value="t" style="margin-right:12px;margin-bottom:4px"/></el-checkbox-group>
            </div>
          </el-form-item></el-col>
          <el-col :span="24"><el-form-item label="URL和IP地址段">
            <el-input v-model="form.url_ip_range" type="textarea" :rows="3"/>
            <div style="font-size:11px;color:#909399;margin-top:2px">互联网IP地址列表，连续IP段以"起始IP-终止IP"表示，多个IP段使用英文逗号分隔。支持IPV4和IPV6</div>
          </el-form-item></el-col>
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
const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref('')
const dlg=ref(false),isEdit=ref(false),editId=ref(null)

const companyTypes=['中外合资','外商独资','民营','上市公司','国企','事业单位']
const industries=['教育','政府','工业制造','市政','证券','质量监督检验检疫','交通','公安','电信','税务','财政','电力','发展改革','工商行政管理','广电','国防科技工业','国土资源','海关','经营性公共互联网','科技','能源','农业','人事劳动和社会保障','商业贸易','审计','水利','铁路','统计','外交','卫生','文化','银行','邮政','国际组织','公共管理/社会保障和社会组织','文化/体育和娱乐业','卫生和社会工作','居民服务/修理和其他服务业','水利/环境和公共','科学研究和技术服务业','租聘和商务','服务业','房地产业','信息运输/软件和信息技术服务业','住宿和餐饮业','交通运输/仓储和邮政业','批发和零售业','建筑业','电力/热力/燃气及水生产和供应业','制造业','采矿业','农/林/牧/渔业','其他(请注明)']
const serviceTypes=['系统开发','产品供应','数据服务','云服务','运营运维和安全服务','集成建设','其他']
const importances=['普通','重要','核心']
const dataLevels=['一般','重要','核心','未分级','不涉及']
const dataLocations=['公有云','私有云','网络运营单位机房','国内第三方托管机房','不涉及']
const dataStorages=['集中存储','分布式存储','分类分级存储','其他','不涉及']
const dbTypes=['采用国外数据库软件','采用开源数据库软件','采用国产数据库软件','不涉及']

const form=reactive({
  company_name:'',credit_code:'',address:'',security_dept:'',security_contact:'',security_phone:'',
  company_type:'',has_foreign_capital:'',industry:'',service_type:'',importance:'',
  url_ip_range:'',data_level:'',data_location:'',data_storage:'',db_type:'',remark:'',
  industryArr:[],serviceTypeArr:[],dataLocationArr:[],dataStorageArr:[],dbTypeArr:[]
})

function resetForm(){Object.assign(form,{company_name:'',credit_code:'',address:'',security_dept:'',security_contact:'',security_phone:'',company_type:'',has_foreign_capital:'',industry:'',service_type:'',importance:'',url_ip_range:'',data_level:'',data_location:'',data_storage:'',db_type:'',remark:'',industryArr:[],serviceTypeArr:[],dataLocationArr:[],dataStorageArr:[],dbTypeArr:[]})}

async function fetchList(){loading.value=true;try{const r=await api.get('/info-systems/supply-chain',{params:{page:page.value,size:size.value,search:search.value}});items.value=r.data.items;total.value=r.data.total}catch{}finally{loading.value=false}}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
function openEdit(r){editId.value=r.id;isEdit.value=true;Object.keys(form).forEach(k=>{if(r[k]!==undefined)form[k]=r[k]||''});form.industryArr=(r.industry||'').split(',').filter(Boolean);form.serviceTypeArr=(r.service_type||'').split(',').filter(Boolean);form.dataLocationArr=(r.data_location||'').split(',').filter(Boolean);form.dataStorageArr=(r.data_storage||'').split(',').filter(Boolean);form.dbTypeArr=(r.db_type||'').split(',').filter(Boolean);dlg.value=true}

async function handleSave(){
  try{
    const data={...form};delete data.industryArr;delete data.serviceTypeArr;delete data.dataLocationArr;delete data.dataStorageArr;delete data.dbTypeArr
    if(isEdit.value){await api.put('/info-systems/supply-chain/'+editId.value,data);ElMessage.success('已更新')}
    else{await api.post('/info-systems/supply-chain',data);ElMessage.success('已创建')}
    dlg.value=false;fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'保存失败')}
}
async function handleDelete(r){try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'});await api.delete('/info-systems/supply-chain/'+r.id);ElMessage.success('已删除');fetchList()}catch{}}
onMounted(fetchList)
</script>
<style scoped>.page{padding:20px}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.page-header h2{margin:0;font-size:20px}.filter-bar{margin-bottom:14px;display:flex;gap:8px;align-items:center}</style>
