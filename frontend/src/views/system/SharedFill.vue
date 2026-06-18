<template>
  <div class="shared-page">
    <div v-if="loading" class="shared-loading">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p>正在加载...</p>
    </div>
    <div v-else-if="error" class="shared-error">
      <el-result icon="error" :title="error" sub-title="请检查链接是否正确，或联系管理员" />
    </div>
    <div v-else class="shared-form-wrap">
      <!-- 密码输入 -->
      <div v-if="needPassword && !verified" class="shared-pwd">
        <h2>{{ info.title || '外链填报' }}</h2>
        <p class="pwd-hint">此链接需要密码访问</p>
        <el-input v-model="password" type="password" placeholder="请输入访问密码" show-password @keyup.enter="verifyPwd" />
        <el-button type="primary" @click="verifyPwd" :loading="verifying" style="margin-top:12px;width:100%">验证</el-button>
      </div>
      <!-- 填报表单 — 与编辑页面完全一致 -->
      <div v-else class="shared-form">
        <div class="shared-header">
          <h2>{{ info.title || '信息填报' }}</h2>
          <el-tag v-if="saved" type="success" size="small">已保存</el-tag>
        </div>

        <!-- ═══ 信息系统表单 ═══ -->
        <template v-if="targetType==='info_system'">
        <el-form :model="form" label-position="top" size="default" class="sc-form">
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><DataBoard /></el-icon></span> 基本情况</div>
            <el-row :gutter="16">
              <el-col :span="16"><el-form-item label="系统名称" required><el-input v-model="form.system_name" placeholder="信息系统的完整名称"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="资产类型"><el-select v-model="form.system_type" style="width:100%"><el-option v-for="t in sysTypes" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="信息系统类型"><el-select v-model="form.sub_type" filterable style="width:100%" clearable><el-option v-for="t in subTypes" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="填报类型"><el-select v-model="form.fill_type" style="width:100%"><el-option v-for="t in fillTypes" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="IP地址"><el-input v-model="form.ip_address" placeholder="多个IP用逗号分隔"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="域名"><el-input v-model="form.domain" placeholder="多个域名逗号分隔"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="入口地址"><el-input v-model="form.entry_url" placeholder="https://xxx.nefu.edu.cn"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="单位名称"><el-input v-model="form.org_name"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="运维单位"><el-input v-model="form.dept_name"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="联系人"><el-input v-model="form.contact"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="电话"><el-input v-model="form.contact_phone"/></el-form-item></el-col>
              <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2"/></el-form-item></el-col>
            </el-row>
          </div>
          <el-divider/>
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Lock /></el-icon></span> 等级保护情况</div>
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="等保系统名称"><el-input v-model="form.djdj_sys_name"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保编号"><el-input v-model="form.djdj_no"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保等级"><el-input v-model="form.djdj_level"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保日期"><el-input v-model="form.djdj_date" type="date"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保状态"><el-select v-model="form.djdj_status" style="width:100%"><el-option v-for="s in djdjStatuses" :key="s" :label="s" :value="s"/></el-select></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="测评单位"><el-input v-model="form.djdj_org"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="ICP备案号"><el-input v-model="form.icp_no"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="ICP备案日期"><el-input v-model="form.icp_date" type="date"/></el-form-item></el-col>
            </el-row>
          </div>
          <el-divider/>
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Briefcase /></el-icon></span> 供应链情况</div>
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="开发厂商"><el-select v-model="form.vendor_name" filterable clearable allow-create style="width:100%"><el-option v-for="n in vendorNames" :key="n" :label="n" :value="n"/></el-select></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="产品名称"><el-input v-model="form.product_name"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="版本号"><el-input v-model="form.product_version"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="厂商联系人"><el-input v-model="form.vendor_contact"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="厂商电话"><el-input v-model="form.vendor_phone"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="运维联系人"><el-input v-model="form.ops_contact"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="运维电话"><el-input v-model="form.ops_phone"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="来源"><el-input v-model="form.source_type" placeholder="自主填报"/></el-form-item></el-col>
            </el-row>
          </div>
          <el-button type="primary" @click="handleSave" :loading="saving" style="width:100%;margin-top:12px">提交保存</el-button>
        </el-form>
        </template>

        <!-- ═══ 供应链表单 ═══ -->
        <template v-else>
        <el-form :model="form" label-position="top" size="default" class="sc-form">

          <!-- 第1节：单位基本信息 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><OfficeBuilding /></el-icon></span> 单位基本信息</div>
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
                    <el-option v-for="t in importances" :key="t" :label="t" :value="t"/>
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
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><User /></el-icon></span> 安全责任信息</div>
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
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Briefcase /></el-icon></span> 服务与行业信息</div>
            <el-form-item label="服务行业">
              <el-checkbox-group v-model="industryArr" class="tag-group">
                <el-checkbox-button v-for="t in industries" :key="t" :label="t" :value="t"/>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="服务类型">
              <el-checkbox-group v-model="serviceTypeArr" class="tag-group">
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
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Coin /></el-icon></span> 数据处理与存储信息</div>
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
                  <el-checkbox-group v-model="dataLocationArr">
                    <el-checkbox v-for="t in dataLocations" :key="t" :label="t" :value="t"/>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="数据存储方式">
                  <el-checkbox-group v-model="dataStorageArr">
                    <el-checkbox v-for="t in dataStorages" :key="t" :label="t" :value="t"/>
                  </el-checkbox-group>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="数据库类型">
              <el-checkbox-group v-model="dbTypeArr">
                <el-checkbox v-for="t in dbTypes" :key="t" :label="t" :value="t"/>
              </el-checkbox-group>
            </el-form-item>
          </div>

          <el-divider />

          <!-- 第5节：备注 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><EditPen /></el-icon></span> 备注信息</div>
            <el-form-item>
              <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="补充说明信息（选填）" />
            </el-form-item>
          </div>

          <el-button type="primary" @click="handleSave" :loading="saving" style="width:100%;margin-top:12px">提交保存</el-button>
        </el-form>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading, OfficeBuilding, User, Briefcase, Coin, EditPen, DataBoard, Lock } from '@element-plus/icons-vue'
import api from '@/api/index'
import { addressOptions } from '@/data/addressOptions.js'

const route = useRoute()
const token = route.params.token
const loading = ref(true), error = ref('')
const needPassword = ref(false), verified = ref(false), verifying = ref(false), password = ref('')
const info = ref({ title: '', has_password: false, target_type: '' })
const targetType = ref('')
const saved = ref(false), saving = ref(false)
const addressArr = ref([])
const vendorNames = ref([])

// 选项数据 — 与编辑页面完全一致
const companyTypes = ['中外合资','外商独资','民营','上市公司','国企','事业单位']
const industries = ['教育','政府','工业制造','市政','证券','质量监督检验检疫','交通','公安','电信','税务','财政','电力','发展改革','工商行政管理','广电','国防科技工业','国土资源','海关','经营性公共互联网','科技','能源','农业','人事劳动和社会保障','商业贸易','审计','水利','铁路','统计','外交','卫生','文化','银行','邮政','国际组织','公共管理/社会保障和社会组织','文化/体育和娱乐业','卫生和社会工作','居民服务/修理和其他服务业','水利/环境和公共','科学研究和技术服务业','租聘和商务','服务业','房地产业','信息运输/软件和信息技术服务业','住宿和餐饮业','交通运输/仓储和邮政业','批发和零售业','建筑业','电力/热力/燃气及水生产和供应业','制造业','采矿业','农/林/牧/渔业','其他(请注明)']
const serviceTypes = ['系统开发','产品供应','数据服务','云服务','运营运维和安全服务','集成建设','其他']
const importances = ['普通','重要','核心']
const dataLevels = ['一般','重要','核心','未分级','不涉及']
const dataLocations = ['公有云','私有云','网络运营单位机房','国内第三方托管机房','不涉及']
const dataStorages = ['集中存储','分布式存储','分类分级存储','其他','不涉及']
const dbTypes = ['采用国外数据库软件','采用开源数据库软件','采用国产数据库软件','不涉及']

// 信息系统选项
const sysTypes = ['信息系统(网站)','移动APP','微信小程序','公众号','其他']
const subTypes = ['网上办事大厅','电子邮件系统','网站群管理系统','教务管理系统','安防监控系统','人事管理系统','科研管理系统','资产管理系统','身份管理系统','电子图书馆系统','校园一卡通系统','财务管理系统','数据平台','0A系统','档案管理系统','迎新管理系统','大型仪器设备共享平台','在线学习平台','实验室管理系统','学生资助系统','外事管理系统','校友管理系统','期刊管理系统','招生管理系统','网盘存储系统','实习就业系统','离校管理系统','网络安全管理平台','智慧教空管理系统','融媒体管理系统','电子签章系统','视频会议系统','健康管理系统','校园楼宇管理系统','后勤管理系统','工会管理系统','党务管理系统','其他']
const fillTypes = ['导入','手动','自动','注销','离线','失效']
const djdjStatuses = ['已备案','未备案','备案中','已过期']

// 复选框数组
const industryArr = ref([]), serviceTypeArr = ref([]), dataLocationArr = ref([]), dataStorageArr = ref([]), dbTypeArr = ref([])

const form = reactive({
  company_name: '', credit_code: '', address: '',
  security_dept: '', security_contact: '', security_phone: '',
  company_type: '', has_foreign_capital: '', importance: '',
  industry: '', service_type: '', url_ip_range: '',
  data_level: '', data_location: '', data_storage: '', db_type: '', remark: '',
  // 信息系统字段
  system_name: '', system_type: '', sub_type: '', fill_type: '',
  ip_address: '', domain: '', entry_url: '', org_name: '', dept_name: '',
  contact: '', contact_phone: '',
  djdj_sys_name: '', djdj_no: '', djdj_level: '', djdj_date: null,
  djdj_status: '', djdj_org: '', icp_no: '', icp_date: null,
  vendor_name: '', product_name: '', product_version: '',
  vendor_contact: '', vendor_phone: '', ops_contact: '', ops_phone: '',
  source_type: ''
})

function parseArr(str) { return str ? str.split(',').map(s => s.trim()).filter(Boolean) : [] }
function resolveAddress(raw) {
  if (!raw) return []
  const parts = raw.split(',').filter(Boolean)
  if (parts.length >= 2) return parts.slice(0, 2)
  const city = parts[0]
  if (!city) return []
  for (const p of addressOptions) {
    if (p.label === city) return [p.value]
    const c = p.children?.find(c => c.label === city)
    if (c) return [p.value, c.value]
  }
  return []
}

async function loadData(pwd = '') {
  loading.value = true
  try {
    const r = await api.get(`/shared-links/shared/${token}`, { params: { password: pwd } })
    info.value = { title: r.data.title, has_password: r.data.has_password, target_type: r.data.target_type }
    targetType.value = r.data.target_type || ''
    needPassword.value = false; verified.value = true
    const d = r.data.data || {}
    Object.keys(form).forEach(k => { if (d[k] != null) form[k] = d[k] })
    // 地址级联
    addressArr.value = resolveAddress(form.address)
    // 初始化复选框
    industryArr.value = parseArr(form.industry)
    serviceTypeArr.value = parseArr(form.service_type)
    dataLocationArr.value = parseArr(form.data_location)
    dataStorageArr.value = parseArr(form.data_storage)
    dbTypeArr.value = parseArr(form.db_type)
  } catch (e) {
    if (e.response?.status === 403) { needPassword.value = true; verified.value = false; if (pwd) ElMessage.error('密码错误') }
    else error.value = e.response?.data?.detail || '加载失败'
  } finally { loading.value = false }
}

async function verifyPwd() { verifying.value = true; await loadData(password.value); verifying.value = false }

async function handleSave() {
  if (!form.company_name) { ElMessage.warning('请输入单位名称'); return }
  saving.value = true
  try {
    // 合并地址和复选框数据
    form.address = addressArr.value.length > 0 ? addressArr.value.join(',') : (form.address || '')
    form.industry = industryArr.value.join(',')
    form.service_type = serviceTypeArr.value.join(',')
    form.data_location = dataLocationArr.value.join(',')
    form.data_storage = dataStorageArr.value.join(',')
    form.db_type = dbTypeArr.value.join(',')
    const params = {}
    if (info.value.has_password || password.value) params.password = password.value
    await api.post(`/shared-links/shared/${token}`, form, { params })
    saved.value = true
    ElMessage.success('保存成功')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}

onMounted(async () => {
  await loadData()
  try { const r = await api.get('/info-systems/supply-chain/names'); vendorNames.value = r.data.items || [] } catch { /* */ }
})
</script>

<style scoped>
.shared-page { max-width: 960px; margin: 0 auto; padding: 24px 20px; }
.shared-loading { text-align: center; padding: 80px 0; color: #909399; }
.shared-error { padding: 40px 0; }
.shared-pwd { max-width: 360px; margin: 80px auto; text-align: center; }
.shared-pwd h2 { margin-bottom: 8px; }
.pwd-hint { color: #909399; font-size: 14px; margin-bottom: 16px; }
.shared-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.shared-header h2 { margin: 0; }
.sc-section { margin-bottom: 4px; }
.sc-section-title { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 600; color: #303133; margin-bottom: 16px; }
.sc-section-icon { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 6px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-size: 14px; }
.tag-group { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
