<template>
  <div class="page">
    <div class="page-header">
      <h2>信息系统维护</h2>
      <div class="header-actions">
        <template v-if="authStore.isAdmin">
          <el-button @click="openImportDlg">导入Excel</el-button>
          <input ref="fileInput" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
          <el-button type="primary" @click="handleExport">导出Excel</el-button>
          <el-button type="warning" @click="handleSync" :loading="syncLoading">数据同步</el-button>
        </template>
        <el-button type="success" @click="openCreate">添加系统</el-button>
      </div>
    </div>
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索名称/IP/域名" clearable style="width:220px" @keyup.enter="fetchList" @clear="fetchList">
        <template #append><el-button :icon="Search" @click="fetchList"/></template>
      </el-input>
      <el-select v-model="filterSysType" placeholder="资产类型" clearable style="width:130px" @change="fetchList">
        <el-option v-for="t in sysTypes" :key="t" :label="t" :value="t"/>
      </el-select>
      <el-select v-model="filterSubType" placeholder="信息系统类型" clearable filterable style="width:150px" @change="fetchList">
        <el-option v-for="t in subTypes" :key="t" :label="t" :value="t"/>
      </el-select>
      <el-input v-model="filterManager" placeholder="管理员" clearable style="width:100px" @keyup.enter="fetchList" @clear="fetchList"/>
      <el-input v-model="filterOwner" placeholder="负责人" clearable style="width:100px" @keyup.enter="fetchList" @clear="fetchList"/>
      <el-select v-model="filterFillType" placeholder="填报状态" clearable style="width:110px" @change="fetchList">
        <el-option v-for="t in ['导入','手动','自动','注销','申请注销','离线','失效']" :key="t" :label="t" :value="t"/>
      </el-select>
      <el-select v-model="filterUrlStatus" placeholder="验证状态" clearable style="width:110px" @change="fetchList">
        <el-option v-for="t in ['在线','离线']" :key="t" :label="t" :value="t"/>
      </el-select>
      <span style="color:#909399;font-size:13px;line-height:32px;white-space:nowrap">共 {{total}} 条</span>
      <el-button v-if="authStore.isAdmin && selectedIds.length>0" type="danger" @click="handleBatchDelete">批量删除 ({{selectedIds.length}})</el-button>
      <el-button v-if="selectedIds.length>0" type="success" size="small" @click="handleBatchClaim">批量认领 ({{selectedIds.length}})</el-button>
      <el-button v-if="selectedIds.length>0" type="warning" size="small" @click="handleBatchRevoke">批量撤销 ({{selectedIds.length}})</el-button>
      <el-button v-if="selectedIds.length>0" type="danger" size="small" @click="handleBatchCancel">申请注销 ({{selectedIds.length}})</el-button>
      <el-button v-if="selectedIds.length>0" size="small" @click="handleBatchUncancel">撤销注销 ({{selectedIds.length}})</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe size="small" @selection-change="onSelect" @sort-change="onSort" :default-sort="{prop:'id',order:'descending'}">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="system_name" label="系统名称" min-width="160" show-overflow-tooltip sortable/>
      <el-table-column prop="system_type" label="资产类型" width="120" sortable/>
      <el-table-column prop="sub_type" label="信息系统类型" width="140" show-overflow-tooltip sortable/>
      <el-table-column prop="ip_address" label="IP" width="130" show-overflow-tooltip sortable/>
      <el-table-column prop="domain" label="域名" min-width="150" show-overflow-tooltip sortable/>
      <el-table-column prop="entry_url" label="入口地址" min-width="160" show-overflow-tooltip sortable/>
      <el-table-column prop="belong_dept_name" label="所属部门" width="120" show-overflow-tooltip sortable/>
      <el-table-column prop="manager_name" label="管理员" width="80" sortable/>
      <el-table-column prop="owner_name" label="负责人" width="80" sortable/>
      <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip sortable/>
      <el-table-column prop="fill_type" label="填报状态" width="90" sortable>
        <template #default="{row}">
          <el-tag :type="row.fill_type==='自动'?'success':row.fill_type==='注销'||row.fill_type==='申请注销'?'danger':row.fill_type==='离线'?'warning':row.fill_type==='失效'?'info':''" size="small">{{row.fill_type||'手动'}}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="url_status" label="验证状态" width="90" sortable>
        <template #default="{row}">
          <el-tag :type="row.url_status==='在线'?'success':'danger'" size="small">{{row.url_status||'-'}}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{row}">
          <template v-if="authStore.isAdmin || row.created_by === authStore.user?.id || (authStore.user?.gh && authStore.user.gh === row.manager_gh)">
            <el-tooltip content="编辑"><el-button link type="primary" :icon="Edit" size="small" @click="openEdit(row)"/></el-tooltip>
            <el-tooltip content="删除"><el-button link type="danger" :icon="Delete" size="small" @click="handleDelete(row)"/></el-tooltip>
          </template>
          <span v-else style="color:#c0c4cc;font-size:12px">-</span>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-if="total>0" v-model:current-page="page" v-model:page-size="size" :page-sizes="[10,20,50,100]" :total="total" layout="total,sizes,prev,pager,next" @current-change="fetchList" @size-change="fetchList" style="justify-content:center;margin-top:16px"/>

    <!-- 编辑/添加对话框 -->
    <el-dialog v-model="dlg" :title="isEdit?'编辑信息系统':'添加信息系统'" width="900px" class="is-dialog" destroy-on-close>
      <template #header="{ title }">
        <div style="display:flex;align-items:center;gap:12px">
          <span>{{ title }}</span>
          <el-button v-if="isEdit" size="small" type="warning" plain @click="openSharedLink">外链填报</el-button>
        </div>
      </template>
      <el-scrollbar max-height="68vh">
        <el-form :model="form" label-position="top" size="default" class="is-form">

          <!-- 基本情况 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><DataBoard /></el-icon></span> 基本情况</div>
            <el-row :gutter="16">
              <el-col :span="8"><el-form-item label="资产ID"><el-input v-model="form.asset_id" disabled/></el-form-item></el-col>
              <el-col :span="16"><el-form-item label="系统名称" required><el-input v-model="form.system_name" placeholder="信息系统的完整名称"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="资产类型"><el-select v-model="form.system_type" style="width:100%"><el-option v-for="t in sysTypes" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="信息系统类型"><el-select v-model="form.sub_type" filterable style="width:100%" clearable><el-option v-for="t in subTypes" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="填报类型"><el-select v-model="form.fill_type" style="width:100%"><el-option v-for="t in ['导入','手动','自动','注销','申请注销','离线','失效']" :key="t" :label="t" :value="t"/></el-select></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="IP地址"><el-input v-model="form.ip_address" placeholder="多个IP用逗号分隔"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="域名"><el-input v-model="form.domain" placeholder="多个域名逗号分隔，不含http"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="入口地址"><el-input v-model="form.entry_url" placeholder="https://xxx.nefu.edu.cn"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="单位名称"><el-input v-model="form.org_name"/></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="运维单位"><el-input v-model="form.dept_name"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="联系人"><el-input v-model="form.contact"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="电话"><el-input v-model="form.contact_phone"/></el-form-item></el-col>
              <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2"/></el-form-item></el-col>
            </el-row>
          </div>

          <el-divider/>

          <!-- 归属信息 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><UserFilled /></el-icon></span> 归属信息</div>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="所属部门">
                  <el-tree-select v-model="form.dept_id" :data="deptOptions" :props="{label:'dwmc',value:'id',children:'children'}" placeholder="选择所属部门" clearable check-strictly filterable style="width:100%"/>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="管理员">
                  <div style="display:flex;align-items:center;gap:6px;width:100%">
                    <el-select v-model="managerSelected" filterable remote :remote-method="(q)=>searchUsers(q,'manager')" :loading="managerSearching" placeholder="输入姓名或工号搜索" clearable style="flex:1" @change="onManagerSelect">
                      <el-option v-for="u in managerOptions" :key="u.id" :label="`${u.name} (${u.gh||u.username})`" :value="u.id"/>
                    </el-select>
                    <el-button :icon="Search" title="从教职工库查询管理员" @click="openStaffLookup('manager')" >查管理员</el-button>
                  </div>
                  <div v-if="form.manager_name" style="margin-top:6px;display:flex;align-items:center;gap:8px">
                    <el-tag type="success" closable @close="clearManager">{{ form.manager_name }}</el-tag>
                    <span style="font-size:12px;color:#909399">工号：{{ form.manager_gh }}</span>
                  </div>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="负责人">
                  <div style="display:flex;align-items:center;gap:6px;width:100%">
                    <el-select v-model="ownerSelected" filterable remote :remote-method="(q)=>searchUsers(q,'owner')" :loading="ownerSearching" placeholder="输入姓名或工号搜索" clearable style="flex:1" @change="onOwnerSelect" :disabled="!!form.owner_gh">
                      <el-option v-for="u in ownerOptions" :key="u.id" :label="`${u.name} (${u.gh||u.username})`" :value="u.id"/>
                    </el-select>
                    <el-button :icon="Search" title="从教职工库查询负责人" @click="openStaffLookup('owner')" :disabled="!!form.owner_gh">查负责人</el-button>
                  </div>
                  <div v-if="form.owner_name" style="margin-top:6px;display:flex;align-items:center;gap:8px">
                    <el-tag type="success" closable @close="clearOwner">{{ form.owner_name }}</el-tag>
                    <span style="font-size:12px;color:#909399">工号：{{ form.owner_gh }}</span>
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-divider/>

          <!-- 等级保护情况 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Lock /></el-icon></span> 等级保护情况</div>
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="等保系统名称"><el-select v-model="form.djdj_sys_name" filterable :filter-method="searchDjdj" :loading="djdjSearching" @focus="loadAllDjdj" @change="onDjdjSelect" clearable style="width:100%"><el-option v-for="d in djdjOptions" :key="d.system_name" :label="d.system_name" :value="d.system_name"/></el-select></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保编号"><el-input v-model="form.djdj_no"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保等级"><el-input v-model="form.djdj_level"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保日期"><el-input v-model="form.djdj_date" type="date"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="等保状态"><el-select v-model="form.djdj_status" style="width:100%" clearable><el-option v-for="s in ['已备案','未备案','备案中','已过期']" :key="s" :label="s" :value="s"/></el-select></el-form-item></el-col>
              <el-col :span="12"><el-form-item label="测评单位"><el-input v-model="form.djdj_org"/></el-form-item></el-col>
            </el-row>
          </div>

          <el-divider/>

          <!-- 供应链情况 -->
          <div class="sc-section">
            <div class="sc-section-title"><span class="sc-section-icon"><el-icon><Briefcase /></el-icon></span> 供应链情况</div>
            <el-row :gutter="16">
              <el-col :span="12"><el-form-item label="开发厂商"><el-select v-model="form.vendor_name" filterable clearable allow-create style="width:100%" @create="(val)=>{vendorNames.push(val);form.vendor_name=val}"><el-option v-for="n in vendorNames" :key="n" :label="n" :value="n"/></el-select></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="产品名称"><el-input v-model="form.product_name"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="版本号"><el-input v-model="form.product_version"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="厂商联系人"><el-input v-model="form.vendor_contact"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="厂商电话"><el-input v-model="form.vendor_phone"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="运维联系人"><el-input v-model="form.ops_contact"/></el-form-item></el-col>
              <el-col :span="6"><el-form-item label="运维电话"><el-input v-model="form.ops_phone"/></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="来源"><el-input v-model="form.source_type" placeholder="自主填报"/></el-form-item></el-col>
            </el-row>
          </div>

        </el-form>
      </el-scrollbar>
      <template #footer>
        <div class="sc-footer">
          <span class="sc-footer-hint" v-if="isEdit">编辑已有记录</span>
          <span class="sc-footer-hint" v-else>填写系统信息后保存</span>
          <div class="sc-footer-actions">
            <el-button @click="dlg=false">取消</el-button>
            <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 人员查询对话框（两步确认） -->
    <el-dialog v-model="staffDlg" title="查询人员" width="720px" append-to-body @closed="staffLookupResults=[]">
      <el-form inline size="small">
        <el-form-item label="姓名"><el-input v-model="staffForm.name" placeholder="输入姓名" style="width:140px"/></el-form-item>
        <el-form-item label="工号"><el-input v-model="staffForm.gh" placeholder="工号" style="width:120px"/></el-form-item>
        <el-form-item><el-button type="primary" :icon="Search" @click="doStaffLookup" :loading="staffLookingUp">查询</el-button></el-form-item>
      </el-form>
      <div v-if="staffLookupResults.length>0" style="margin-top:8px;max-height:380px;overflow-y:auto">
        <el-radio-group v-model="staffSelectedIdx" class="staff-radio-group">
          <el-radio v-for="(s,idx) in staffLookupResults" :key="idx" :value="idx" class="staff-radio-item" border>
            <div class="staff-card">
              <div class="staff-card-row">
                <strong class="staff-card-name">{{s.name}}</strong>
                <span v-if="s.gh" class="staff-card-gh">工号 {{s.gh}}</span>
                <el-tag size="small" :type="s.source==='系统用户'?'success':s.source.includes('中台')?'warning':'info'" style="margin-left:auto;flex-shrink:0">{{s.source}}</el-tag>
              </div>
              <div class="staff-card-row staff-card-meta" v-if="s.phone||s.mobile||s.department_name">
                <span v-if="s.phone" class="staff-card-info"><el-icon><Phone /></el-icon> {{s.phone}}</span>
                <span v-if="s.mobile" class="staff-card-info"><el-icon><Iphone /></el-icon> {{s.mobile}}</span>
                <span v-if="s.department_name" class="staff-card-info"><el-icon><OfficeBuilding /></el-icon> {{s.department_name}}</span>
              </div>
            </div>
          </el-radio>
        </el-radio-group>
      </div>
      <div v-if="staffLookedUp && staffLookupResults.length===0" style="color:#909399;margin-top:8px">未找到匹配的人员</div>
      <template #footer>
        <el-button @click="staffDlg=false">取消</el-button>
        <el-button type="primary" @click="confirmStaffSelect" :disabled="staffSelectedIdx===null">确定并选择</el-button>
      </template>
    </el-dialog>

    <!-- 导入对话框 -->
    <el-dialog v-model="importDlg" title="导入信息系统数据" width="560px" append-to-body>
      <el-form label-width="90px" size="default">
        <el-form-item label="选择文件">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" accept=".xlsx" :on-change="onImportFileSelect" :on-remove="onImportFileRemove" :file-list="importFileList" drag>
            <el-icon style="font-size:36px;color:#409eff"><component is="UploadFilled"/></el-icon>
            <div style="margin-top:8px">拖拽或点击选择 .xlsx 文件</div>
            <template #tip><div style="font-size:12px;color:#909399;margin-top:4px">支持：资产导出.xlsx、资产清单.xlsx、信息系统管理_*.xlsx（自动识别格式）</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item label="去重策略" v-if="importFile">
          <el-radio-group v-model="importMode" size="small">
            <el-radio-button value="supplement">补充空白</el-radio-button>
            <el-radio-button value="overwrite">覆盖已有</el-radio-button>
            <el-radio-button value="skip">跳过重复</el-radio-button>
          </el-radio-group>
          <div style="font-size:12px;color:#909399;margin-top:4px">
            <template v-if="importMode==='supplement'">系统名称相同 → 仅将 Excel 中的非空值填入系统的空白字段</template>
            <template v-else-if="importMode==='overwrite'">系统名称相同 → 使用 Excel 数据完全替换</template>
            <template v-else>系统名称相同 → 跳过不导入</template>
          </div>
        </el-form-item>
      </el-form>
      <div v-if="importResult" class="import-result">
        <el-alert :title="importResult.message" :type="importResult.created>0?'success':'info'" :closable="false" show-icon/>
        <div class="import-stats">
          <span>总计 <b>{{importResult.total}}</b></span>
          <span style="color:#67c23a">新建 <b>{{importResult.created}}</b></span>
          <span style="color:#409eff">覆盖 <b>{{importResult.updated}}</b></span>
          <span style="color:#e6a23c">补充 <b>{{importResult.supplemented}}</b></span>
          <span style="color:#909399">跳过 <b>{{importResult.skipped}}</b></span>
          <span v-if="importResult.dept_matched" style="color:#67c23a">匹配部门 <b>{{importResult.dept_matched}}</b></span>
          <span v-if="importResult.users_created" style="color:#e6a23c">新增用户 <b>{{importResult.users_created}}</b></span>
          <span v-if="importResult.supply_added" style="color:#e6a23c">新增供应链 <b>{{importResult.supply_added}}</b></span>
          <span v-if="importResult.errors" style="color:#f56c6c">失败 <b>{{importResult.errors}}</b></span>
        </div>
      </div>
      <template #footer>
        <el-button @click="importDlg=false">关闭</el-button>
        <el-button type="primary" @click="doImport" :loading="importing" :disabled="!importFile">开始导入</el-button>
      </template>
    </el-dialog>

    <!-- 外链管理对话框 -->
    <el-dialog v-model="linkDlg" title="外链填报" width="560px" append-to-body @opened="loadLinks">
      <el-form label-width="80px" size="default">
        <el-form-item label="外链标题">
          <el-input v-model="linkForm.title" placeholder="如：信息系统信息填报" />
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
      <div v-if="links.length > 0" style="margin-top:16px">
        <el-divider />
        <div style="font-size:14px;font-weight:500;margin-bottom:8px">已有外链</div>
        <div v-for="l in links" :key="l.token" class="link-item">
          <div class="link-info">
            <div><b>{{ l.title }}</b></div>
            <div class="link-url">{{ origin }}{{ l.url }}</div>
            <div class="link-meta">
              {{ l.has_password ? '需密码' : '无密码' }} · {{ l.access_count || 0 }}次访问
              · {{ l.expire_at ? '过期:'+new Date(l.expire_at).toLocaleString('zh-CN') : '永不过期' }}
              · <el-tag :type="l.is_active?'success':'danger'" size="small">{{ l.is_active?'有效':'已关闭' }}</el-tag>
            </div>
          </div>
          <div class="link-actions">
            <el-button size="small" @click="copyLink(l)">复制链接</el-button>
            <el-button size="small" :type="l.is_active?'warning':'success'" @click="toggleLink(l)">{{ l.is_active?'关闭':'开启' }}</el-button>
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
import { Search, Edit, Delete, DataBoard, UserFilled, Lock, Briefcase, UploadFilled, Phone, Iphone, OfficeBuilding } from '@element-plus/icons-vue'
import { useAuthStore } from '@/store/auth'
import api from '@/api/index'

const authStore=useAuthStore()
const items=ref([]),loading=ref(false),page=ref(1),size=ref(20),total=ref(0),search=ref('')
const filterSysType=ref(''),filterSubType=ref(''),filterManager=ref(''),filterOwner=ref(''),filterFillType=ref(''),filterUrlStatus=ref('')
const selectedIds=ref([]),dlg=ref(false),isEdit=ref(false),editId=ref(null),fileInput=ref(null),syncLoading=ref(false),saving=ref(false)
const sortField=ref(''),sortOrder=ref('')
function onSort({prop,order}){sortField.value=prop||'';sortOrder.value=order==='ascending'?'asc':'desc';page.value=1;fetchList()}
const djdjSearching=ref(false),djdjOptions=ref([]),vendorNames=ref([]),deptOptions=ref([])
// 导入相关
const importDlg=ref(false),importing=ref(false),importFile=ref(null),importMode=ref('supplement'),importResult=ref(null)
const importFileList=ref([]),uploadRef=ref(null)

// 管理员/负责人选择
const managerSelected=ref(null),ownerSelected=ref(null)
const managerOptions=ref([]),ownerOptions=ref([])
const managerSearching=ref(false),ownerSearching=ref(false)

// 人员查询对话框
const staffDlg=ref(false),staffLookingUp=ref(false)
const staffTarget=ref('')
const staffForm=reactive({name:'',gh:''})
const staffLookupResults=ref([])
const staffLookedUp=ref(false)
const staffSelectedIdx=ref(null)

const sysTypes=['信息系统(网站)','移动APP','微信小程序','公众号','其他']
const subTypes=['网上办事大厅','电子邮件系统','网站群管理系统','教务管理系统','安防监控系统','人事管理系统','科研管理系统','资产管理系统','身份管理系统','电子图书馆系统','校园一卡通系统','财务管理系统','数据平台','0A系统','档案管理系统','迎新管理系统','大型仪器设备共享平台','在线学习平台','实验室管理系统','学生资助系统','外事管理系统','校友管理系统','期刊管理系统','招生管理系统','网盘存储系统','实习就业系统','离校管理系统','网络安全管理平台','智慧教空管理系统','融媒体管理系统','电子签章系统','视频会议系统','健康管理系统','校园楼宇管理系统','后勤管理系统','工会管理系统','党务管理系统','其他']

const form=reactive({
  asset_id:'',system_name:'',system_type:'',sub_type:'',ip_address:'',domain:'',
  org_name:'',dept_name:'',contact:'',contact_phone:'',fill_type:'手动',
  dept_id:null, manager_name:'',manager_gh:'',owner_name:'',owner_gh:'',
  djdj_no:'',djdj_level:'',djdj_date:null,djdj_sys_name:'',djdj_status:'',djdj_org:'',icp_no:'',icp_date:null,
  entry_url:'',url_status:'',
  remark:'',vendor_name:'',product_name:'',product_version:'',source_type:'',
  vendor_contact:'',vendor_phone:'',ops_contact:'',ops_phone:''
})

const baseForm=()=>({
  asset_id:'',system_name:'',system_type:'',sub_type:'',ip_address:'',domain:'',
  org_name:'',dept_name:'',contact:'',contact_phone:'',fill_type:'手动',
  dept_id:null, manager_name:'',manager_gh:'',owner_name:'',owner_gh:'',
  djdj_no:'',djdj_level:'',djdj_date:null,djdj_sys_name:'',djdj_status:'',djdj_org:'',icp_no:'',icp_date:null,
  entry_url:'',url_status:'',
  remark:'',vendor_name:'',product_name:'',product_version:'',source_type:'',
  vendor_contact:'',vendor_phone:'',ops_contact:'',ops_phone:''
})

// 显式列出所有可编辑字段（不依赖 Object.keys 枚举 Vue reactive Proxy，避免枚举遗漏）
const SAVE_FIELDS = [
  'asset_id','system_name','system_type','sub_type','ip_address','domain',
  'org_name','dept_name','contact','contact_phone','fill_type',
  'dept_id','manager_name','manager_gh','owner_name','owner_gh',
  'djdj_no','djdj_level','djdj_date','djdj_sys_name','djdj_status','djdj_org',
  'icp_no','icp_date',
  'entry_url','url_status',
  'remark','vendor_name','product_name','product_version','source_type',
  'vendor_contact','vendor_phone','ops_contact','ops_phone'
]
const INT_FIELDS = ['dept_id']
const DATE_FIELDS = ['djdj_date','icp_date']

function onSelect(v){selectedIds.value=v.map(r=>r.id)}

function resetForm(){
  Object.assign(form, baseForm())
  managerSelected.value=null; ownerSelected.value=null
  managerOptions.value=[]; ownerOptions.value=[]
  djdjOptions.value=[]
}

async function fetchList(){loading.value=true;try{const p={page:page.value,size:size.value,search:search.value,system_type:filterSysType.value,sub_type:filterSubType.value,manager_name:filterManager.value,owner_name:filterOwner.value,fill_type:filterFillType.value,url_status:filterUrlStatus.value};if(sortField.value){p.sort_field=sortField.value;p.sort_order=sortOrder.value}const r=await api.get('/info-systems',{params:p});items.value=r.data.items;total.value=r.data.total}catch{}finally{loading.value=false}}
function openCreate(){resetForm();isEdit.value=false;dlg.value=true}
function openEdit(r){
  resetForm()  // 先清空所有字段，防止上次编辑/新建的残留数据泄漏
  editId.value=r.id; isEdit.value=true
  // 使用显式字段列表逐字段赋值（避免 Proxy 枚举问题）
  for(const k of SAVE_FIELDS){
    if(r[k] !== undefined){
      if(k === 'dept_id'){
        form.dept_id = (r[k] != null && r[k] !== '') ? parseInt(r[k]) : null
      }else{
        form[k] = (r[k] != null) ? r[k] : ''
      }
    }
  }
  // 还原管理员/负责人显示
  managerSelected.value=null; ownerSelected.value=null; managerOptions.value=[]; ownerOptions.value=[]
  if(r.manager_name){
    managerOptions.value=[{id:0,name:r.manager_name,gh:r.manager_gh,username:''}]
    managerSelected.value=0
  }
  if(r.owner_name){
    ownerOptions.value=[{id:0,name:r.owner_name,gh:r.owner_gh,username:''}]
    ownerSelected.value=0
  }
  // 预加载等保选项（编辑时需显示已选值）
  if(r.djdj_sys_name){
    djdjOptions.value=[{system_name:r.djdj_sys_name,record_no:r.djdj_no,level:r.djdj_level,record_date:r.djdj_date,eval_org:r.djdj_org}]
  }else{
    djdjOptions.value=[]
  }
  dlg.value=true
}

// ── 用户搜索 ──
async function searchUsers(q,target){
  if(!q||q.length<1)return
  if(target==='manager')managerSearching.value=true;else ownerSearching.value=true
  try{
    const r=await api.get('/info-systems/staff-search',{params:{q}})
    const list=r.data.items||[]
    if(target==='manager'){managerOptions.value=list;managerSearching.value=false}
    else{ownerOptions.value=list;ownerSearching.value=false}
  }catch{if(target==='manager')managerSearching.value=false;else ownerSearching.value=false}
}
function onManagerSelect(id){
  const u=managerOptions.value.find(x=>String(x.id)===String(id))
  if(u){form.manager_name=u.name;form.manager_gh=u.gh||u.username}
  else{form.manager_name='';form.manager_gh=''}
}
function onOwnerSelect(id){
  const u=ownerOptions.value.find(x=>String(x.id)===String(id))
  if(u){form.owner_name=u.name;form.owner_gh=u.gh||u.username}
  else{form.owner_name='';form.owner_gh=''}
}
function clearManager(){form.manager_name='';form.manager_gh='';managerSelected.value=null;managerOptions.value=[]}
function clearOwner(){form.owner_name='';form.owner_gh='';ownerSelected.value=null;ownerOptions.value=[]}

// ── 人员查询（两步确认） ──
function openStaffLookup(target){
  staffTarget.value=target
  staffForm.name='';staffForm.gh=''
  staffLookupResults.value=[];staffLookedUp.value=false;staffSelectedIdx.value=null
  staffDlg.value=true
}
async function doStaffLookup(){
  if(!staffForm.name&&!staffForm.gh){ElMessage.warning('请至少填写姓名或工号');return}
  staffLookingUp.value=true;staffLookedUp.value=false;staffSelectedIdx.value=null
  try{
    const q=staffForm.name||staffForm.gh
    const r=await api.get('/info-systems/staff-lookup',{params:{q}})
    staffLookupResults.value=r.data.items||[]
    staffLookedUp.value=true
    if(staffLookupResults.value.length===0)ElMessage.info('未找到匹配的人员')
  }catch(e){ElMessage.error(e.response?.data?.detail||'查询失败')}
  finally{staffLookingUp.value=false}
}
async function confirmStaffSelect(){
  const s=staffLookupResults.value[staffSelectedIdx.value]
  if(!s)return
  // 如果是系统用户，直接选
  if(s.source==='系统用户'){
    applyStaffToForm(s)
    staffDlg.value=false
    ElMessage.success('已选择人员')
    return
  }
  // 从教职工库/数据中台注册（API自动补全个人信息）
  try{
    const r=await api.post('/info-systems/staff-register',{name:s.name,gh:s.gh})
    const u=r.data
    applyStaffToForm(u)
    staffDlg.value=false
    ElMessage.success(u.message||'已添加并选择人员')
  }catch(e){ElMessage.error(e.response?.data?.detail||'注册失败')}
}
function applyStaffToForm(u){
  if(staffTarget.value==='manager'){
    managerOptions.value=[{id:u.id,name:u.name,gh:u.gh,username:u.username}]
    managerSelected.value=u.id
    form.manager_name=u.name;form.manager_gh=u.gh||u.username
    console.log('[applyStaffToForm] 设置管理员:', u.name, u.gh)
  }else{
    ownerOptions.value=[{id:u.id,name:u.name,gh:u.gh,username:u.username}]
    ownerSelected.value=u.id
    form.owner_name=u.name;form.owner_gh=u.gh||u.username
    console.log('[applyStaffToForm] 设置负责人:', u.name, u.gh)
  }
}

// ── 等保查询 ──
const allDjdjLoaded = ref(false)
const allDjdj = ref([])
async function loadAllDjdj(){
  if(allDjdjLoaded.value){djdjOptions.value=allDjdj.value;return}
  djdjSearching.value=true
  try{
    const r=await api.get('/info-systems/djdj',{params:{size:100}})
    allDjdj.value=r.data.items||[]
    djdjOptions.value=allDjdj.value
    allDjdjLoaded.value=true
  }catch{}finally{djdjSearching.value=false}
}
function searchDjdj(q){
  if(!q){djdjOptions.value=allDjdj.value;return}
  djdjOptions.value=allDjdj.value.filter(d=>d.system_name&&d.system_name.includes(q))
}
function onDjdjSelect(name){
  const d=djdjOptions.value.find(d=>d.system_name===name)
  if(d){form.djdj_no=d.record_no;form.djdj_level=d.level;form.djdj_date=d.record_date;form.djdj_org=d.eval_org||d.dept_name||'';form.djdj_status=form.djdj_status||'已备案';form.org_name=form.org_name||d.org_name}
}

async function handleSave(){
  saving.value=true
  try{
    // 必填校验
    if(!form.system_name||!form.system_name.trim()){ElMessage.warning('请输入系统名称');saving.value=false;return}
    // 从 form 显式提取每个字段（避免 Proxy 枚举问题）
    const data={}
    for(const k of SAVE_FIELDS){
      let v=form[k]
      if(v===undefined)continue
      // Integer 字段：空值 → null
      if(INT_FIELDS.includes(k)){
        data[k]=(v!=null&&v!=='')?parseInt(v):null
        continue
      }
      // Date 字段：空值 → null
      if(DATE_FIELDS.includes(k)){
        if(v===''||v===null||v===undefined)data[k]=null
        else data[k]=v
        continue
      }
      // 字符串字段：保留原值
      data[k]=(v!=null)?v:''
    }
    console.log('Saving:', isEdit.value?'PUT':'POST', JSON.stringify(data))
    if(isEdit.value){
      await api.put('/info-systems/'+editId.value,data)
      ElMessage.success('已更新')
    }else{
      const r=await api.post('/info-systems',data)
      console.log('Created:',r.data)
      ElMessage.success('已创建')
    }
    dlg.value=false;fetchList()
  }catch(e){
    console.error('Save error:',e)
    const detail=e.response?.data?.detail
    if(detail&&typeof detail==='string'&&e.response?.status<500){
      ElMessage.error(detail)
    }else if(!e.response){
      // 网络错误已在拦截器处理
    }else if(e.response?.status>=500){
      // 已在拦截器显示
    }else{
      ElMessage.error('保存失败，请稍后重试')
    }
  }
  finally{saving.value=false}
}

async function handleBatchClaim(){
  if(!selectedIds.value.length) return
  try{await api.post('/info-systems/batch-claim',{model:'info_system',ids:selectedIds.value});ElMessage.success('批量认领成功');selectedIds.value=[];fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'认领失败')}
}
async function handleBatchRevoke(){
  if(!selectedIds.value.length) return
  try{await ElMessageBox.confirm('确定撤销选中的认领？','确认',{type:'warning'})}catch{return}
  try{
    await api.post('/info-systems/batch-revoke',{model:'info_system',ids:selectedIds.value})
    ElMessage.success('已撤销')
    selectedIds.value=[]
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail || '撤销失败，可能是权限不足')}
}
async function handleBatchCancel(){
  if(!selectedIds.value.length) return
  try{
    await api.post('/assets/batch-cancel',{ids:selectedIds.value,type:'info_system'})
    ElMessage.success('已申请注销')
    selectedIds.value=[]
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'申请注销失败')}
}
async function handleBatchUncancel(){
  if(!selectedIds.value.length) return
  try{
    await api.post('/assets/batch-uncancel',{ids:selectedIds.value,type:'info_system'})
    ElMessage.success('已撤销注销')
    selectedIds.value=[]
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'撤销注销失败')}
}
async function handleDelete(r){
  try{await ElMessageBox.confirm('确定删除?','确认',{type:'warning'})}catch{return}
  try{
    await api.delete('/info-systems/'+r.id)
    ElMessage.success('已删除')
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail || '删除失败，可能是权限不足')}
}
async function handleBatchDelete(){
  try{await ElMessageBox.confirm('确定删除选中的 '+selectedIds.value.length+' 条记录?','批量删除',{type:'error'})}catch{return}
  try{
    await api.post('/info-systems/batch-delete',{ids:selectedIds.value})
    ElMessage.success('已删除')
    selectedIds.value=[]
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail || '批量删除失败，需要管理员权限')}
}
async function handleSync(){syncLoading.value=true;try{const r=await api.post('/info-systems/sync-from-platform');ElMessage.success(r.data.message);console.log('Sync stats:',r.data.stats);fetchList()}catch(e){ElMessage.error(e.response?.data?.detail||'同步失败')}finally{syncLoading.value=false}}
function openImportDlg(){importDlg.value=true;importFile.value=null;importFileList.value=[];importResult.value=null;importMode.value='supplement'}
function onImportFileSelect(uploadFile){importFile.value=uploadFile.raw}
function onImportFileRemove(){importFile.value=null;importResult.value=null}
async function doImport(){
  if(!importFile.value){ElMessage.warning('请选择文件');return}
  importing.value=true;importResult.value=null
  try{
    const fd=new FormData();fd.append('file',importFile.value)
    const r=await api.post('/info-systems/import?mode='+importMode.value,fd)
    importResult.value=r.data
    ElMessage.success(r.data.message)
    fetchList()
  }catch(e){ElMessage.error(e.response?.data?.detail||'导入失败')}
  finally{importing.value=false}
}
async function handleExport(){try{const r=await api.get('/info-systems/export',{responseType:'blob'});const url=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=url;a.download='info_systems.xlsx';a.click()}catch{}}

async function loadDepts(){try{const r=await api.get('/sys/departments/tree?all=true');deptOptions.value=r.data}catch{}}

// ── 外链填报 ──
const linkDlg=ref(false),linkCreating=ref(false),links=ref([])
const linkForm=reactive({title:'',password:'',expire_hours:24})
const origin=window.location.origin

function openSharedLink(){
  linkForm.title='信息系统填报 - '+(form.system_name||'')
  linkForm.password='';linkForm.expire_hours=24;linkDlg.value=true
}
async function loadLinks(){
  try{const r=await api.get('/shared-links/by-target',{params:{target_type:'info_system',target_id:editId.value}});links.value=r.data.items||[]}catch{links.value=[]}
}
async function createLink(){
  if(!editId.value)return;linkCreating.value=true
  try{
    const r=await api.post('/shared-links',{target_type:'info_system',target_id:editId.value,title:linkForm.title,password:linkForm.password,expire_hours:linkForm.expire_hours})
    const url=origin+r.data.url
    navigator.clipboard.writeText(url).then(()=>ElMessage.success('外链已生成并复制')).catch(()=>ElMessage.success('外链已生成'))
    await loadLinks()
  }catch(e){ElMessage.error(e.response?.data?.detail||'生成失败')}finally{linkCreating.value=false}
}
async function toggleLink(l){try{const r=await api.put('/shared-links/'+l.token+'/toggle');ElMessage.success(r.data.message);await loadLinks()}catch(e){ElMessage.error(e.response?.data?.detail||'操作失败')}}
async function deleteLink(l){try{await ElMessageBox.confirm('确定删除此外链？','确认',{type:'warning'});await api.delete('/shared-links/'+l.token);ElMessage.success('已删除');await loadLinks()}catch{}}
function copyLink(l){const url=origin+l.url;navigator.clipboard.writeText(url).then(()=>ElMessage.success('已复制')).catch(()=>ElMessage.warning('复制失败'))}

onMounted(async()=>{fetchList();try{const r=await api.get('/info-systems/supply-chain/names');vendorNames.value=r.data.items}catch{};loadDepts()})
</script>
<style scoped>
.page{padding:20px}
.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.page-header h2{margin:0;font-size:20px}
.header-actions{display:flex;gap:8px}
.filter-bar{margin-bottom:14px;display:flex;gap:8px;align-items:center}

.sc-section{margin-bottom:4px}
.sc-section-title{display:flex;align-items:center;gap:8px;font-size:15px;font-weight:600;color:#303133;margin-bottom:16px}
.sc-section-icon{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:6px;background:linear-gradient(135deg,var(--color-primary,#6366f1),#8b5cf6);color:#fff;font-size:14px}
.is-form :deep(.el-form-item){margin-bottom:14px}
.is-form :deep(.el-form-item__label){padding-bottom:4px;color:#606266;font-weight:500}
.is-form :deep(.el-divider--horizontal){margin:8px 0 20px}

.user-pick{display:flex;gap:8px;align-items:center}
.user-pick-meta{margin-top:4px}
/* 已选人员信息行 */
.sc-footer{display:flex;justify-content:space-between;align-items:center;width:100%}
.sc-footer-hint{font-size:12px;color:#909399}
.sc-footer-actions{display:flex;gap:8px}

.is-dialog :deep(.el-dialog__body){padding:16px 24px}

/* 人员查询结果 */
.staff-radio-group{display:flex;flex-direction:column;gap:6px;width:100%}
.staff-radio-item{width:100%;margin:0!important;padding:12px 16px;min-height:56px}
.staff-radio-item .el-radio__label{width:100%;padding-left:10px}
.staff-card{display:flex;flex-direction:column;gap:6px;width:100%}
.staff-card-row{display:flex;align-items:center;gap:12px;line-height:1.6}
.staff-card-name{font-size:14px;min-width:50px;white-space:nowrap}
.staff-card-gh{font-size:12px;color:#909399;white-space:nowrap}
.staff-card-meta{gap:16px;flex-wrap:wrap}
.staff-card-info{display:inline-flex;align-items:center;gap:3px;font-size:12px;color:#606266;white-space:nowrap}
.staff-card-info .el-icon{font-size:13px;color:#909399}
/* 导入结果 */
.import-result{margin-top:16px}
.import-stats{display:flex;gap:16px;margin-top:8px;padding:10px 14px;background:#f5f7fa;border-radius:6px;font-size:13px}
.import-stats b{font-size:16px;margin-left:2px}
.link-item{display:flex;align-items:center;justify-content:space-between;padding:12px;margin-bottom:8px;background:#f5f7fa;border-radius:6px;gap:12px}
.link-info{flex:1;min-width:0}
.link-info b{font-size:14px}
.link-url{font-size:12px;color:#409eff;word-break:break-all;margin:4px 0;font-family:monospace}
.link-meta{font-size:12px;color:#909399}
.link-actions{display:flex;gap:4px;flex-shrink:0}
</style>
