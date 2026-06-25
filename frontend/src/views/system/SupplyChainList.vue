<template>
  <div class="page">
    <div class="page-header">
      <h2>供应链信息维护</h2>
      <div class="header-actions">
        <template v-if="authStore.isAdmin">
          <el-button @click="triggerImport">导入Excel</el-button>
          <input ref="fileInput" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
          <el-button type="primary" @click="handleExport">导出Excel</el-button>
        </template>
        <el-button type="success" @click="openCreate">添加单位</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索单位名称" clearable style="width:260px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList" /></template>
      </el-input>
      <span style="color:#909399;font-size:13px;line-height:32px">共 {{total}} 条</span>
      <el-button v-if="authStore.isAdmin && selectedIds.length>0" type="danger" @click="handleBatchDelete">批量删除 ({{selectedIds.length}})</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" @selection-change="onSelect">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="company_name" label="单位名称" min-width="200" show-overflow-tooltip/>
      <el-table-column prop="credit_code" label="信用代码" width="180"/>
      <el-table-column prop="company_type" label="类型" width="100"/>
      <el-table-column prop="importance" label="重要程度" width="80"/>
      <el-table-column prop="security_contact" label="联系人" width="80"/>
      <el-table-column prop="security_phone" label="电话" width="120"/>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{row}">
          <template v-if="authStore.isAdmin || row.created_by === authStore.user?.id">
            <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" size="small" @click="openEdit(row)"/></el-tooltip>
            <el-tooltip content="删除"><el-button link type="danger" :icon="Delete" size="small" @click="handleDelete(row)"/></el-tooltip>
          </template>
          <span v-else style="color:#c0c4cc;font-size:12px">-</span>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <!-- 编辑/添加对话框 -->
    <el-dialog v-model="dlg" :title="isEdit?'编辑供应链单位':'添加供应链单位'" width="960px" class="sc-dialog" destroy-on-close>
      <template #header="{ title }">
        <div style="display:flex;align-items:center;gap:12px">
          <span>{{ title }}</span>
          <el-button v-if="isEdit" size="small" type="warning" plain @click="openSharedLink">外链填报</el-button>
        </div>
      </template>
      <el-scrollbar max-height="70vh">
        <el-form :model="form" label-position="top" size="default" class="sc-form">

          <!-- 第1节：单位基本信息 -->
          <div class="sc-section">
            <div class="sc-section-title">
              <span class="sc-section-icon"><el-icon><OfficeBuilding /></el-icon></span> 单位基本信息
            </div>
            <el-row :gutter="20">
              <el-col :span="16">
                <el-form-item label="单位名称" required>
                  <el-input v-model="form.company_name" placeholder="请输入供应链单位全称" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="统一社会信用代码">
                  <el-input v-model="form.credit_code" placeholder="18位信用代码" clearable maxlength="18" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="单位类型">
                  <el-select v-model="form.company_type" placeholder="选择类型" clearable style="width:100%">
                    <el-option v-for="t in companyTypes" :key="t" :label="t" :value="t"/>
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="是否具有境外资本">
                  <el-radio-group v-model="form.has_foreign_capital">
                    <el-radio value="是">是</el-radio>
                    <el-radio value="否">否</el-radio>
                  </el-radio-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="重要程度">
                  <el-select v-model="form.importance" placeholder="选择重要程度" clearable style="width:100%">
                    <el-option v-for="t in importances" :key="t" :label="t" :value="t">
                      <span class="importance-option">
                        <span class="importance-dot" :class="'dot-'+t"></span>
                        {{ t }}
                      </span>
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="24">
                <el-form-item label="注册地址">
                  <el-cascader v-model="addressArr" :options="addressOptions" placeholder="请选择省份/城市" clearable filterable style="width:100%" />
                  <div v-if="form.address && addressArr.length===0" style="margin-top:4px;font-size:12px;color:#909399">
                    当前值：{{ form.address }}（请重新选择）
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-divider />

          <!-- 第2节：安全责任信息 -->
          <div class="sc-section">
            <div class="sc-section-title">
              <span class="sc-section-icon"><el-icon><User /></el-icon></span> 安全责任信息
            </div>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="内部网络安全责任部门">
                  <el-input v-model="form.security_dept" placeholder="如：技术部、安全运维中心" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="直接联系人">
                  <el-input v-model="form.security_contact" placeholder="联系人姓名" clearable />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item label="联系电话">
                  <el-input v-model="form.security_phone" placeholder="手机号码" clearable />
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-divider />

          <!-- 第3节：服务与行业信息 -->
          <div class="sc-section">
            <div class="sc-section-title">
              <span class="sc-section-icon"><el-icon><Briefcase /></el-icon></span> 服务与行业信息
            </div>
            <el-form-item label="服务行业">
              <div class="tag-select">
                <el-checkbox-group v-model="form.industryArr" @change="form.industry=form.industryArr.join(',')" class="tag-group">
                  <el-checkbox-button v-for="t in industries" :key="t" :label="t" :value="t" class="tag-item"/>
                </el-checkbox-group>
              </div>
            </el-form-item>
            <el-form-item label="服务类型">
              <el-checkbox-group v-model="form.serviceTypeArr" @change="form.service_type=form.serviceTypeArr.join(',')">
                <el-checkbox-button v-for="t in serviceTypes" :key="t" :label="t" :value="t"/>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="互联网URL及IP地址段">
              <el-input v-model="form.url_ip_range" type="textarea" :rows="2" placeholder="URL 地址、IP地址段，多个以英文逗号分隔&#10;如：https://example.com, 10.0.0.1-10.0.0.255" />
            </el-form-item>
          </div>

          <el-divider />

          <!-- 第4节：数据处理信息 -->
          <div class="sc-section">
            <div class="sc-section-title">
              <span class="sc-section-icon"><el-icon><Coin /></el-icon></span> 数据处理与存储信息
            </div>
            <el-row :gutter="20">
              <el-col :span="8">
                <el-form-item label="处理数据最高级别">
                  <el-select v-model="form.data_level" placeholder="选择级别" clearable style="width:100%">
                    <el-option v-for="t in dataLevels" :key="t" :label="t" :value="t"/>
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="数据存储位置">
                  <el-checkbox-group v-model="form.dataLocationArr" @change="form.data_location=form.dataLocationArr.join(',')">
                    <el-checkbox v-for="t in dataLocations" :key="t" :label="t" :value="t"/>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="数据存储方式">
                  <el-checkbox-group v-model="form.dataStorageArr" @change="form.data_storage=form.dataStorageArr.join(',')">
                    <el-checkbox v-for="t in dataStorages" :key="t" :label="t" :value="t"/>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="数据库类型">
              <el-checkbox-group v-model="form.dbTypeArr" @change="form.db_type=form.dbTypeArr.join(',')">
                <el-checkbox v-for="t in dbTypes" :key="t" :label="t" :value="t"/>
              </el-checkbox-group>
            </el-form-item>
          </div>

          <el-divider />

          <!-- 第5节：备注 -->
          <div class="sc-section">
            <div class="sc-section-title">
              <span class="sc-section-icon"><el-icon><EditPen /></el-icon></span> 备注信息
            </div>
            <el-form-item>
              <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="补充说明信息（选填）" />
            </el-form-item>
          </div>

        </el-form>
      </el-scrollbar>
      <template #footer>
        <div class="sc-footer">
          <span class="sc-footer-hint" v-if="isEdit">编辑已有记录，修改后点击保存</span>
          <span class="sc-footer-hint" v-else>填写供应链单位信息后保存</span>
          <div class="sc-footer-actions">
            <el-button @click="dlg=false">取消</el-button>
            <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 外链管理对话框 -->
    <el-dialog v-model="linkDlg" title="外链填报" width="560px" append-to-body @opened="loadLinks">
      <el-form label-width="80px" size="default">
        <el-form-item label="外链标题">
          <el-input v-model="linkForm.title" placeholder="如：供应链信息填报-XX公司" />
        </el-form-item>
        <el-form-item label="访问密码">
          <el-input v-model="linkForm.password" placeholder="留空则不设密码" show-password />
        </el-form-item>
        <el-form-item label="失效时间">
          <el-select v-model="linkForm.expire_hours" style="width:200px">
            <el-option label="永不过期" :value="0" />
            <el-option label="1小时" :value="1" />
            <el-option label="6小时" :value="6" />
            <el-option label="24小时" :value="24" />
            <el-option label="48小时" :value="48" />
            <el-option label="7天" :value="168" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="createLink" :loading="linkCreating">生成外链</el-button>
        </el-form-item>
      </el-form>
      <!-- 已有外链列表 -->
      <div v-if="links.length > 0" style="margin-top:16px">
        <el-divider />
        <div style="font-size:14px;font-weight:500;margin-bottom:8px">已有外链</div>
        <div v-for="l in links" :key="l.token" class="link-item">
          <div class="link-info">
            <div><b>{{ l.title }}</b></div>
            <div class="link-url">{{ origin }}{{ l.url }}</div>
            <div class="link-meta">
              {{ l.has_password ? '需密码' : '无密码' }}
              · {{ l.access_count || 0 }}次访问
              · {{ l.expire_at ? '过期: '+new Date(l.expire_at).toLocaleString('zh-CN') : '永不过期' }}
              · <el-tag :type="l.is_active?'success':'danger'" size="small">{{ l.is_active ? '有效' : '已关闭' }}</el-tag>
            </div>
          </div>
          <div class="link-actions">
            <el-button size="small" @click="copyLink(l)">复制链接</el-button>
            <el-button size="small" :type="l.is_active?'warning':'success'" @click="toggleLink(l)">{{ l.is_active ? '关闭' : '开启' }}</el-button>
            <el-button size="small" type="danger" @click="deleteLink(l)">删除</el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, OfficeBuilding, User, Briefcase, Coin, EditPen, Edit, Delete } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'
import { addressOptions } from '@/data/addressOptions.js'

const authStore=useAuthStore()
const origin = window.location.origin
const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref('')
const selectedIds=ref([]),dlg=ref(false),isEdit=ref(false),editId=ref(null),saving=ref(false)
const addressArr=ref([])  // 级联地址选择器
const fileInput=ref(null)

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

function resetForm(){Object.assign(form,{company_name:'',credit_code:'',address:'',security_dept:'',security_contact:'',security_phone:'',company_type:'',has_foreign_capital:'',industry:'',service_type:'',importance:'',url_ip_range:'',data_level:'',data_location:'',data_storage:'',db_type:'',remark:'',industryArr:[],serviceTypeArr:[],dataLocationArr:[],dataStorageArr:[],dbTypeArr:[]});addressArr.value=[]}
function onSelect(v){selectedIds.value=v.map(r=>r.id)}

async function fetchList(){loading.value=true;try{const r=await api.get('/info-systems/supply-chain',{params:{page:page.value,size:size.value,search:search.value}});items.value=r.data.items;total.value=r.data.total}catch{}finally{loading.value=false}}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
function resolveAddress(raw) {
  // 解析地址字符串为级联数组 [省份, 城市]
  if (!raw) return []
  const parts = raw.split(',').filter(Boolean)
  if (parts.length >= 2) return parts.slice(0, 2)
  // 单段：可能是城市名，尝试在全部省份中查找
  const city = parts[0]
  for (const p of addressOptions) {
    if (p.label === city) return [p.value]
    const c = p.children?.find(c => c.label === city)
    if (c) return [p.value, c.value]
  }
  return [] // 无法匹配
}
function openEdit(r){editId.value=r.id;isEdit.value=true;Object.keys(form).forEach(k=>{if(r[k]!==undefined)form[k]=r[k]||''});form.industryArr=(r.industry||'').split(',').filter(Boolean);form.serviceTypeArr=(r.service_type||'').split(',').filter(Boolean);form.dataLocationArr=(r.data_location||'').split(',').filter(Boolean);form.dataStorageArr=(r.data_storage||'').split(',').filter(Boolean);form.dbTypeArr=(r.db_type||'').split(',').filter(Boolean);addressArr.value=resolveAddress(r.address);dlg.value=true}

async function handleSave(){
  saving.value=true
  try{
    if(!form.company_name){ElMessage.warning('请输入单位名称');saving.value=false;return}
    const data={...form};delete data.industryArr;delete data.serviceTypeArr;delete data.dataLocationArr;delete data.dataStorageArr;delete data.dbTypeArr
    data.address = addressArr.value.length > 0 ? addressArr.value.join(',') : (form.address || '')
    if(isEdit.value){await api.put('/info-systems/supply-chain/'+editId.value,data);ElMessage.success('已更新')}
    else{await api.post('/info-systems/supply-chain',data);ElMessage.success('已创建')}
    dlg.value=false;fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'保存失败')}
  finally{saving.value=false}
}
async function handleDelete(r){
  try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'})}catch{return}
  try{await api.delete('/info-systems/supply-chain/'+r.id);ElMessage.success('已删除');fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'删除失败，可能是权限不足')}
}
async function handleBatchDelete(){
  try{await ElMessageBox.confirm('确定删除选中的 '+selectedIds.value.length+' 条记录?','批量删除',{type:'error'})}catch{return}
  try{await api.post('/info-systems/supply-chain/batch-delete',{ids:selectedIds.value});ElMessage.success('已删除');selectedIds.value=[];fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'批量删除失败，需要管理员权限')}
}
function triggerImport(){fileInput.value?.click()}
async function onFileChange(e){const file=e.target.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);loading.value=true;try{const r=await api.post('/info-systems/supply-chain/import',fd);ElMessage.success(r.data.message);fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'导入失败')}finally{loading.value=false;e.target.value=''}}
async function handleExport(){try{const r=await api.get('/info-systems/supply-chain/export',{responseType:'blob'});const url=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=url;a.download='supply_chain_export.xlsx';a.click();URL.revokeObjectURL(url)}catch{}}
// ── 外链填报 ──
const linkDlg = ref(false)
const linkCreating = ref(false)
const links = ref([])
const linkForm = reactive({ title: '', password: '', expire_hours: 24 })

async function openSharedLink() {
  linkForm.title = '供应链信息填报 - ' + (form.company_name || '')
  linkForm.password = ''
  linkForm.expire_hours = 24
  linkDlg.value = true
}

async function loadLinks() {
  try {
    const r = await api.get('/shared-links/by-target', { params: { target_type: 'supply_chain', target_id: editId.value } })
    links.value = r.data.items || []
  } catch { links.value = [] }
}

async function createLink() {
  if (!editId.value) return
  linkCreating.value = true
  try {
    const r = await api.post('/shared-links', {
      target_type: 'supply_chain', target_id: editId.value,
      title: linkForm.title, password: linkForm.password,
      expire_hours: linkForm.expire_hours,
    })
    // 自动复制到剪贴板
    const url = window.location.origin + r.data.url
    navigator.clipboard.writeText(url).then(() => {
      ElMessage.success('外链已生成并复制到剪贴板')
    }).catch(() => {
      ElMessage.success('外链已生成')
    })
    await loadLinks()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '生成失败') }
  finally { linkCreating.value = false }
}

async function toggleLink(l) {
  try {
    const r = await api.put(`/shared-links/${l.token}/toggle`)
    ElMessage.success(r.data.message)
    await loadLinks()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function deleteLink(l) {
  try {
    await ElMessageBox.confirm('确定删除此外链？', '确认', { type: 'warning' })
    await api.delete(`/shared-links/${l.token}`)
    ElMessage.success('已删除')
    await loadLinks()
  } catch { /* 取消 */ }
}

function copyLink(l) {
  const url = window.location.origin + l.url
  navigator.clipboard.writeText(url).then(() => ElMessage.success('链接已复制')).catch(() => ElMessage.warning('复制失败，请手动复制'))
}

onMounted(fetchList)
</script>

<style scoped>
/* ═══════════════ 页面 ═══════════════ */
.page{padding:20px}
.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.page-header h2{margin:0;font-size:20px}
.header-actions{display:flex;gap:8px}
.filter-bar{margin-bottom:14px;display:flex;gap:10px;align-items:center}

/* ═══════════════ 对话框表单 ═══════════════ */
.sc-section{margin-bottom:4px}
.sc-section-title{
  display:flex;align-items:center;gap:8px;
  font-size:15px;font-weight:600;color:#303133;
  margin-bottom:16px;padding-bottom:8px;
}
.sc-section-icon{
  display:flex;align-items:center;justify-content:center;
  width:28px;height:28px;border-radius:6px;
  background:linear-gradient(135deg,var(--color-primary,#6366f1),#8b5cf6);
  color:#fff;font-size:14px;
}

/* label-position="top" 的间距微调 */
.sc-form :deep(.el-form-item){margin-bottom:16px}
.sc-form :deep(.el-form-item__label){padding-bottom:4px;color:#606266;font-weight:500}
.sc-form :deep(.el-input__wrapper){box-shadow:0 0 0 1px #dcdfe6 inset;transition:box-shadow .2s}
.sc-form :deep(.el-input__wrapper:hover){box-shadow:0 0 0 1px #c0c4cc inset}
.sc-form :deep(.el-textarea__inner){transition:border-color .2s}

/* 重要程度选项 */
.importance-option{display:flex;align-items:center;gap:6px}
.importance-dot{width:8px;height:8px;border-radius:50%}
.dot-普通{background:#909399}
.dot-重要{background:#e6a23c}
.dot-核心{background:#f56c6c}

/* el-divider 优化 */
.sc-form :deep(.el-divider--horizontal){margin:8px 0 20px}

/* 行业标签选择 */
.tag-select{max-height:180px;overflow-y:auto;border:1px solid #e4e7ed;border-radius:8px;padding:10px;background:#fafafa}
.tag-select:hover{border-color:#c0c4cc}
.tag-group{display:flex;flex-wrap:wrap;gap:6px}
.tag-item :deep(.el-checkbox-button__inner){border-radius:4px!important;border:1px solid #dcdfe6!important;font-size:12px;padding:4px 10px}
.tag-item :deep(.is-checked .el-checkbox-button__inner){background:var(--color-primary,#6366f1);border-color:var(--color-primary,#6366f1)!important;box-shadow:none}

/* checkbox-button 通用 */
:deep(.el-checkbox-button__inner){border-radius:4px;font-size:12px;padding:4px 12px}

/* 单列 checkbox 布局 */
:deep(.el-checkbox-group:not(.tag-group)){display:flex;flex-wrap:wrap;gap:4px 12px}

/* 对话框底部 */
.sc-footer{display:flex;justify-content:space-between;align-items:center;width:100%}
.sc-footer-hint{font-size:12px;color:#909399}
.sc-footer-actions{display:flex;gap:8px}

/* 对话框整体滚动 */
.sc-dialog :deep(.el-dialog__body){padding:16px 24px}

/* ═══════════════ 外链 ═══════════════ */
.link-item { display: flex; align-items: center; justify-content: space-between; padding: 12px; margin-bottom: 8px; background: #f5f7fa; border-radius: 6px; gap: 12px; }
.link-info { flex: 1; min-width: 0; }
.link-info b { font-size: 14px; }
.link-url { font-size: 12px; color: #409eff; word-break: break-all; margin: 4px 0; font-family: monospace; }
.link-meta { font-size: 12px; color: #909399; }
.link-actions { display: flex; gap: 4px; flex-shrink: 0; }
</style>
