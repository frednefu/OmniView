<template>
  <div class="backup-manage">
    <div class="page-header">
      <h2>系统备份</h2>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- ═══════════ 任务管理 ═══════════ -->
      <el-tab-pane label="任务管理" name="jobs">
        <div class="toolbar">
          <el-button type="primary" @click="openCreate">
            <el-icon><Plus /></el-icon> 新建备份任务
          </el-button>
        </div>

        <el-table :data="jobList" v-loading="jobLoading" stripe>
          <el-table-column prop="name" label="任务名称" min-width="140" />
          <el-table-column label="备份模式" width="80">
            <template #default="{ row }">
              <el-tag :type="row.mode === 'ftp' ? 'warning' : 'success'" size="small">
                {{ row.mode === 'ftp' ? 'FTP' : '本地' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="调度" width="160">
            <template #default="{ row }">
              <span class="cron-text">{{ cronLabel(row.cron_expression) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备份内容" width="200">
            <template #default="{ row }">
              <el-tag
                v-for="c in contentTags(row.backup_contents)" :key="c.value"
                size="small" class="content-tag"
                :type="c.type"
              >{{ c.label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="保留" width="80" align="center">
            <template #default="{ row }">
              {{ row.retention_days === 0 ? '永久' : row.retention_days + '天' }}
            </template>
          </el-table-column>
          <el-table-column label="启用" width="70" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.enabled"
                size="small"
                @change="toggleEnabled(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="上次执行" width="160">
            <template #default="{ row }">
              <template v-if="row.last_run_at">
                <div class="last-run">{{ formatTime(row.last_run_at) }}</div>
                <el-tag
                  :type="row.last_status === 'success' ? 'success' : row.last_status === 'failed' ? 'danger' : 'info'"
                  size="small"
                >{{ row.last_status === 'success' ? '成功' : row.last_status === 'failed' ? '失败' : '—' }}</el-tag>
              </template>
              <span v-else class="text-muted">未执行</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="runJob(row)">
                <el-icon><VideoPlay /></el-icon>
              </el-button>
              <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-popconfirm title="确定删除此备份任务？" @confirm="deleteJob(row.id)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-if="jobTotal > jobPageSize"
          v-model:current-page="jobPage"
          :page-size="jobPageSize"
          :total="jobTotal"
          layout="total, prev, pager, next"
          @current-change="fetchJobs"
          style="margin-top: 16px; justify-content: flex-end;"
        />
      </el-tab-pane>

      <!-- ═══════════ 备份历史 ═══════════ -->
      <el-tab-pane label="备份历史" name="history">
        <div class="toolbar">
          <el-select v-model="historyJobFilter" placeholder="按任务筛选" clearable @change="fetchHistory" style="width: 180px;">
            <el-option v-for="j in jobList" :key="j.id" :label="j.name" :value="j.id" />
          </el-select>
          <el-select v-model="historyStatusFilter" placeholder="按状态筛选" clearable @change="fetchHistory" style="width: 120px; margin-left: 8px;">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="运行中" value="running" />
          </el-select>
          <el-button @click="fetchHistory" style="margin-left: 8px;">刷新</el-button>
        </div>

        <el-table :data="historyList" v-loading="historyLoading" stripe>
          <el-table-column label="时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.started_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="job_name" label="任务名称" min-width="120" />
          <el-table-column prop="content_summary" label="备份内容" min-width="160" />
          <el-table-column label="文件大小" width="100" align="right">
            <template #default="{ row }">
              {{ formatSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column label="存储位置" width="80">
            <template #default="{ row }">
              <el-tag :type="row.storage_location === 'ftp' ? 'warning' : 'success'" size="small">
                {{ row.storage_location === 'ftp' ? 'FTP' : '本地' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="80" align="right">
            <template #default="{ row }">
              {{ formatDuration(row.duration_seconds) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'"
                size="small"
              >{{ row.status === 'success' ? '成功' : row.status === 'failed' ? '失败' : '运行中' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="已验证" width="70" align="center">
            <template #default="{ row }">
              <el-icon v-if="row.verified" color="#10b981"><CircleCheckFilled /></el-icon>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="downloadBackup(row.id)">
                <el-icon><Download /></el-icon> 下载
              </el-button>
              <el-button link type="success" size="small" :loading="verifyingId === row.id" @click="verifyBackup(row)">
                验证
              </el-button>
              <el-button link type="info" size="small" @click="showLog(row.id)">
                <el-icon><Document /></el-icon> 日志
              </el-button>
              <el-popconfirm title="确定删除此备份记录及文件？" @confirm="deleteHistory(row.id)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-if="historyTotal > historyPageSize"
          v-model:current-page="historyPage"
          :page-size="historyPageSize"
          :total="historyTotal"
          layout="total, prev, pager, next"
          @current-change="fetchHistory"
          style="margin-top: 16px; justify-content: flex-end;"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- ═══════════ 创建/编辑对话框 ═══════════ -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑备份任务' : '新建备份任务'"
      width="700px"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入任务名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>

        <el-divider content-position="left">备份模式</el-divider>
        <el-form-item label="备份模式" prop="mode">
          <el-radio-group v-model="form.mode">
            <el-radio value="local">本地备份</el-radio>
            <el-radio value="ftp">远程 FTP</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.mode === 'local'">
          <el-form-item label="备份目录" prop="local_path">
            <el-input v-model="form.local_path" placeholder="例如：/data/backups" />
          </el-form-item>
        </template>

        <template v-if="form.mode === 'ftp'">
          <el-form-item label="服务器地址" prop="ftp_host">
            <el-input v-model="form.ftp_host" placeholder="FTP 服务器 IP 或域名" />
          </el-form-item>
          <el-form-item label="端口" prop="ftp_port">
            <el-input-number v-model="form.ftp_port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="用户名" prop="ftp_user">
            <el-input v-model="form.ftp_user" placeholder="FTP 用户名" />
          </el-form-item>
          <el-form-item label="密码" prop="ftp_password">
            <el-input v-model="form.ftp_password" type="password" show-password placeholder="FTP 密码" />
          </el-form-item>
          <el-form-item label="远程目录" prop="ftp_remote_path">
            <el-input v-model="form.ftp_remote_path" placeholder="/backups" />
          </el-form-item>
          <el-form-item label=" ">
            <el-button :loading="ftpTesting" @click="testFtp">测试连接</el-button>
          </el-form-item>
        </template>

        <el-divider content-position="left">备份内容</el-divider>
        <el-form-item label="备份内容" prop="backup_contents">
          <el-checkbox-group v-model="form.contentList">
            <el-checkbox label="database">数据库 (MySQL)</el-checkbox>
            <el-checkbox label="configs">系统配置文件</el-checkbox>
            <el-checkbox label="images">Docker 镜像</el-checkbox>
            <el-checkbox label="uploads">上传文件</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-divider content-position="left">调度配置</el-divider>
        <el-form-item label="调度模式">
          <el-select v-model="cronPreset" @change="onCronPresetChange" style="width: 140px;">
            <el-option label="每天" value="daily" />
            <el-option label="每周" value="weekly" />
            <el-option label="每月" value="monthly" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>

        <template v-if="cronPreset === 'daily'">
          <el-form-item label="执行时间">
            <el-time-picker v-model="cronTime" format="HH:mm" placeholder="选择时间" @change="buildCron" />
          </el-form-item>
        </template>
        <template v-if="cronPreset === 'weekly'">
          <el-form-item label="执行时间">
            <el-time-picker v-model="cronTime" format="HH:mm" placeholder="选择时间" @change="buildCron" />
          </el-form-item>
          <el-form-item label="星期">
            <el-select v-model="cronWeekDays" multiple placeholder="选择星期" @change="buildCron" style="width: 100%;">
              <el-option v-for="(d, i) in weekOptions" :key="i" :label="d" :value="i" />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="cronPreset === 'monthly'">
          <el-form-item label="执行时间">
            <el-time-picker v-model="cronTime" format="HH:mm" placeholder="选择时间" @change="buildCron" />
          </el-form-item>
          <el-form-item label="日期">
            <el-input-number v-model="cronMonthDay" :min="1" :max="28" @change="buildCron" />
          </el-form-item>
        </template>
        <template v-if="cronPreset === 'custom'">
          <el-form-item label="Cron 表达式">
            <div class="cron-fields">
              <span>秒</span><el-input-number v-model="cronFields[0]" :min="0" :max="59" @change="buildCron" size="small" />
              <span>分</span><el-input-number v-model="cronFields[1]" :min="0" :max="59" @change="buildCron" size="small" />
              <span>时</span><el-input-number v-model="cronFields[2]" :min="0" :max="23" @change="buildCron" size="small" />
              <span>日</span><el-input v-model="cronFields[3]" @change="buildCron" size="small" style="width:50px;" />
              <span>月</span><el-input v-model="cronFields[4]" @change="buildCron" size="small" style="width:50px;" />
              <span>周</span><el-input v-model="cronFields[5]" @change="buildCron" size="small" style="width:50px;" />
            </div>
          </el-form-item>
          <el-form-item label="预览">
            <el-tag type="info">{{ cronPreview }}</el-tag>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="Cron">
            <el-tag type="info">{{ form.cron_expression }}</el-tag>
            <span class="cron-preview">{{ cronPreview }}</span>
          </el-form-item>
        </template>

        <el-divider content-position="left">保留策略</el-divider>
        <el-form-item label="保留天数">
          <el-input-number v-model="form.retention_days" :min="0" :max="3650" />
          <span style="margin-left: 8px; color: var(--color-text-muted);">0 = 永久保留</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ═══════════ 验证结果对话框 ═══════════ -->
    <el-dialog v-model="verifyDialogVisible" title="验证结果" width="500px">
      <div v-if="verifyResult">
        <el-alert
          :type="verifyResult.success ? 'success' : 'warning'"
          :title="verifyResult.success ? '验证通过' : '验证发现问题'"
          :closable="false"
          style="margin-bottom: 16px;"
        />
        <div v-for="c in verifyResult.checks" :key="c" class="verify-check">{{ c }}</div>
      </div>
    </el-dialog>

    <!-- ═══════════ 备份日志对话框 ═══════════ -->
    <el-dialog v-model="logDialogVisible" title="备份过程日志" width="750px" destroy-on-close>
      <div v-if="logLoading" style="text-align: center; padding: 40px;">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      </div>
      <div v-else-if="logData" class="log-container">
        <div class="log-header">
          <span>任务：{{ logData.job_name }}</span>
          <el-tag :type="logData.status === 'success' ? 'success' : logData.status === 'failed' ? 'danger' : 'warning'" size="small">
            {{ logData.status === 'success' ? '成功' : logData.status === 'failed' ? '失败' : '运行中' }}
          </el-tag>
        </div>
        <pre class="log-output">{{ logData.log_output || '（无日志输出）' }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, VideoPlay, Download, CircleCheckFilled, Document, Loading } from '@element-plus/icons-vue'
import {
  getBackupJobs, createBackupJob, updateBackupJob, deleteBackupJob, runBackupJob,
  getBackupHistory, deleteBackupHistory, verifyBackup as verifyBackupApi,
  testFtpConnection, getDownloadUrl, getBackupLog,
} from '@/api/backup'

// ── 标签页 ────────────────────────────────────────────────
const activeTab = ref('jobs')

// ── 任务列表 ──────────────────────────────────────────────
const jobList = ref([])
const jobLoading = ref(false)
const jobPage = ref(1)
const jobPageSize = ref(20)
const jobTotal = ref(0)

async function fetchJobs() {
  jobLoading.value = true
  try {
    const res = await getBackupJobs({ page: jobPage.value, page_size: jobPageSize.value })
    jobList.value = res.items
    jobTotal.value = res.total
  } catch { /* */ }
  finally { jobLoading.value = false }
}

// ── 历史列表 ──────────────────────────────────────────────
const historyList = ref([])
const historyLoading = ref(false)
const historyPage = ref(1)
const historyPageSize = ref(20)
const historyTotal = ref(0)
const historyJobFilter = ref(null)
const historyStatusFilter = ref(null)

async function fetchHistory() {
  historyLoading.value = true
  try {
    const params = { page: historyPage.value, page_size: historyPageSize.value }
    if (historyJobFilter.value) params.job_id = historyJobFilter.value
    if (historyStatusFilter.value) params.status = historyStatusFilter.value
    const res = await getBackupHistory(params)
    historyList.value = res.items
    historyTotal.value = res.total
  } catch { /* */ }
  finally { historyLoading.value = false }
}

// ── 创建/编辑对话框 ──────────────────────────────────────
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const submitLoading = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  name: '',
  enabled: true,
  mode: 'local',
  local_path: '',
  ftp_host: '',
  ftp_port: 21,
  ftp_user: '',
  ftp_password: '',
  ftp_remote_path: '',
  contentList: ['database', 'configs', 'images', 'uploads'],
  cron_expression: '0 2 * * *',
  retention_days: 30,
})
const form = reactive(defaultForm())

const formRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  mode: [{ required: true, message: '请选择备份模式', trigger: 'change' }],
  local_path: [{ required: true, message: '请输入备份目录路径', trigger: 'blur' }],
}

function resetForm() {
  Object.assign(form, defaultForm())
  cronPreset.value = 'daily'
  cronTime.value = new Date(2024, 0, 1, 2, 0)
  cronWeekDays.value = []
  cronMonthDay.value = 1
  cronFields.value = ['0', '*', '*', '*', '*', '*']
  editId.value = null
  isEdit.value = false
}

function openCreate() {
  resetForm()
  dialogVisible.value = true
}

async function openEdit(row) {
  isEdit.value = true
  editId.value = row.id
  const job = await getBackupJob(row.id)
  form.name = job.name
  form.enabled = job.enabled
  form.mode = job.mode
  form.local_path = job.local_path || ''
  form.ftp_host = job.ftp_host || ''
  form.ftp_port = job.ftp_port || 21
  form.ftp_user = job.ftp_user || ''
  form.ftp_password = job.ftp_password || ''
  form.ftp_remote_path = job.ftp_remote_path || ''
  form.contentList = (job.backup_contents || 'database,configs,images,uploads').split(',').filter(Boolean)
  form.cron_expression = job.cron_expression || '0 2 * * *'
  form.retention_days = job.retention_days ?? 30
  // 解析 cron 到 UI 状态
  parseCronExpression(job.cron_expression || '0 2 * * *')
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!form.name) { ElMessage.warning('请输入任务名称'); return }
  if (form.mode === 'local' && !form.local_path) { ElMessage.warning('请输入本地备份目录路径'); return }
  if (form.mode === 'ftp' && !form.ftp_host) { ElMessage.warning('请输入 FTP 服务器地址'); return }
  if (!form.contentList.length) { ElMessage.warning('请至少选择一项备份内容'); return }

  submitLoading.value = true
  try {
    const data = {
      name: form.name,
      enabled: form.enabled,
      mode: form.mode,
      local_path: form.local_path || null,
      ftp_host: form.ftp_host || null,
      ftp_port: form.ftp_port,
      ftp_user: form.ftp_user || null,
      ftp_password: form.ftp_password || null,
      ftp_remote_path: form.ftp_remote_path || null,
      backup_contents: form.contentList.join(','),
      cron_expression: form.cron_expression,
      retention_days: form.retention_days,
    }
    if (isEdit.value) {
      await updateBackupJob(editId.value, data)
      ElMessage.success('备份任务已更新')
    } else {
      await createBackupJob(data)
      ElMessage.success('备份任务已创建')
    }
    dialogVisible.value = false
    fetchJobs()
  } catch (e) {
    // axios interceptor handles error messages
  } finally {
    submitLoading.value = false
  }
}

async function deleteJob(id) {
  try {
    await deleteBackupJob(id)
    ElMessage.success('备份任务已删除')
    fetchJobs()
  } catch { /* */ }
}

async function runJob(row) {
  try {
    await ElMessageBox.confirm(`确定立即执行备份任务「${row.name}」？`, '手动执行备份')
    await runBackupJob(row.id)
    ElMessage.success('备份任务已提交，请稍后查看备份历史')
    setTimeout(fetchHistory, 2000)
  } catch { /* user cancelled */ }
}

async function toggleEnabled(row) {
  try {
    await updateBackupJob(row.id, { enabled: !row.enabled })
    row.enabled = !row.enabled
    ElMessage.success(row.enabled ? '已启用' : '已禁用')
  } catch { /* */ }
}

// ── 下载 ─────────────────────────────────────────────────
function downloadBackup(id) {
  window.open(getDownloadUrl(id), '_blank')
}

// ── 验证 ─────────────────────────────────────────────────
const verifyingId = ref(null)
const verifyDialogVisible = ref(false)
const verifyResult = ref(null)

async function verifyBackup(row) {
  verifyingId.value = row.id
  try {
    const res = await verifyBackupApi(row.id)
    verifyResult.value = res
    verifyDialogVisible.value = true
    // 刷新历史列表以更新 verified 状态
    if (res.success) fetchHistory()
  } catch { /* */ }
  finally { verifyingId.value = null }
}

// ── 日志 ─────────────────────────────────────────────────
const logDialogVisible = ref(false)
const logLoading = ref(false)
const logData = ref(null)

async function showLog(id) {
  logDialogVisible.value = true
  logLoading.value = true
  logData.value = null
  try {
    logData.value = await getBackupLog(id)
  } catch { /* */ }
  finally { logLoading.value = false }
}

// ── 删除历史 ─────────────────────────────────────────────
async function deleteHistory(id) {
  try {
    await deleteBackupHistory(id)
    ElMessage.success('备份记录已删除')
    fetchHistory()
  } catch { /* */ }
}

// ── FTP 测试 ─────────────────────────────────────────────
const ftpTesting = ref(false)

async function testFtp() {
  if (!form.ftp_host) { ElMessage.warning('请输入 FTP 服务器地址'); return }
  if (!form.ftp_user) { ElMessage.warning('请输入 FTP 用户名'); return }
  ftpTesting.value = true
  try {
    const res = await testFtpConnection({
      host: form.ftp_host,
      port: form.ftp_port,
      user: form.ftp_user,
      password: form.ftp_password,
    })
    if (res.success) {
      ElMessage.success(res.message)
    } else {
      ElMessage.error(res.message)
    }
  } catch { /* */ }
  finally { ftpTesting.value = false }
}

// ── Cron 可视化配置 ──────────────────────────────────────
const cronPreset = ref('daily')
const cronTime = ref(new Date(2024, 0, 1, 2, 0))
const cronWeekDays = ref([])
const cronMonthDay = ref(1)
const cronFields = ref(['0', '*', '*', '*', '*', '*'])

const weekOptions = ['日', '一', '二', '三', '四', '五', '六']

const cronPreview = computed(() => {
  return cronLabel(form.cron_expression)
})

function parseCronExpression(expr) {
  const parts = (expr || '0 2 * * *').trim().split(/\s+/)
  cronFields.value = [
    parts[0] || '0', parts[1] || '*', parts[2] || '*',
    parts[3] || '*', parts[4] || '*', parts[5] || '*',
  ]

  // 智能检测预设模式
  const [s, m, h, d, mo, w] = parts
  if (h && m && d === '*' && mo === '*' && w === '*') {
    // 可能是每天
    if (s === '0') {
      cronPreset.value = 'daily'
      cronTime.value = new Date(2024, 0, 1, parseInt(h), parseInt(m))
      return
    }
  }
  if (h && m && d === '*' && mo === '*' && w !== '*' && w !== '?') {
    // 可能是每周
    cronPreset.value = 'weekly'
    cronTime.value = new Date(2024, 0, 1, parseInt(h) || 0, parseInt(m) || 0)
    cronWeekDays.value = w.split(',').map(x => parseInt(x)).filter(x => !isNaN(x))
    return
  }
  if (h && m && d !== '*' && mo === '*' && (w === '*' || w === '?')) {
    // 可能是每月
    cronPreset.value = 'monthly'
    cronTime.value = new Date(2024, 0, 1, parseInt(h) || 0, parseInt(m) || 0)
    cronMonthDay.value = parseInt(d) || 1
    return
  }
  // 自定义
  cronPreset.value = 'custom'
}

function onCronPresetChange() {
  if (cronPreset.value === 'daily') {
    cronWeekDays.value = []
    cronMonthDay.value = 1
  } else if (cronPreset.value === 'weekly') {
    cronMonthDay.value = 1
  } else if (cronPreset.value === 'monthly') {
    cronWeekDays.value = []
  }
  buildCron()
}

function buildCron() {
  let expr = '0 * * * * *'
  const t = cronTime.value
  let h = '2', m = '0'
  if (t) {
    h = String(t.getHours ? t.getHours() : 2)
    m = String(t.getMinutes ? t.getMinutes() : 0)
  }

  switch (cronPreset.value) {
    case 'daily':
      expr = `0 ${m} ${h} * * *`
      break
    case 'weekly':
      const wd = cronWeekDays.value.length ? cronWeekDays.value.join(',') : '*'
      expr = `0 ${m} ${h} * * ${wd}`
      break
    case 'monthly':
      const md = cronMonthDay.value || 1
      expr = `0 ${m} ${h} ${md} * *`
      break
    case 'custom':
      expr = cronFields.value.join(' ')
      break
  }
  form.cron_expression = expr
}

// ── 工具函数 ─────────────────────────────────────────────
function cronLabel(expr) {
  if (!expr) return '—'
  const parts = expr.trim().split(/\s+/)
  if (parts.length < 6) return expr
  const [, m, h, d, mo, w] = parts

  if (h && m && d === '*' && mo === '*' && w === '*') {
    return `每天 ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  }
  if (h && m && d === '*' && mo === '*' && w !== '*' && w !== '?') {
    const days = w.split(',').map(x => weekOptions[parseInt(x)] || x)
    return `每周${days.join('、')} ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  }
  if (h && m && d !== '*' && mo === '*') {
    return `每月${d}日 ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
  }
  return expr
}

const contentTypeMap = {
  database: { label: '数据库', type: 'primary' },
  configs: { label: '配置文件', type: 'success' },
  images: { label: 'Docker镜像', type: 'warning' },
  uploads: { label: '上传文件', type: 'info' },
}

function contentTags(contents) {
  return (contents || '').split(',').filter(Boolean).map(c => ({
    value: c,
    label: (contentTypeMap[c] || { label: c }).label,
    type: (contentTypeMap[c] || { type: '' }).type,
  }))
}

function formatTime(t) {
  if (!t) return '—'
  const d = new Date(t)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatDuration(secs) {
  if (!secs && secs !== 0) return '—'
  if (secs < 60) return secs + '秒'
  if (secs < 3600) return Math.floor(secs / 60) + '分' + (secs % 60) + '秒'
  return Math.floor(secs / 3600) + '时' + Math.floor((secs % 3600) / 60) + '分'
}

function onTabChange(tab) {
  if (tab === 'history') fetchHistory()
}

onMounted(() => {
  fetchJobs()
})
</script>

<style scoped>
.backup-manage {
  max-width: 1400px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
}

.toolbar {
  margin-bottom: 16px;
}

.content-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.last-run {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.text-muted {
  color: var(--color-text-muted);
  font-size: 13px;
}

.cron-text {
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.cron-fields {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.cron-fields span {
  font-size: 12px;
  color: var(--color-text-secondary);
  min-width: 20px;
}

.cron-preview {
  margin-left: 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.verify-check {
  padding: 4px 0;
  font-size: 14px;
  color: var(--color-text);
}

.log-container {
  background: #1e1e2e;
  border-radius: 8px;
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #181825;
  border-bottom: 1px solid #313244;
  color: #cdd6f4;
  font-size: 14px;
  font-weight: 500;
}

.log-output {
  margin: 0;
  padding: 16px;
  background: #1e1e2e;
  color: #a6e3a1;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 500px;
  overflow-y: auto;
}

.log-output::-webkit-scrollbar {
  width: 6px;
}

.log-output::-webkit-scrollbar-track {
  background: #181825;
}

.log-output::-webkit-scrollbar-thumb {
  background: #45475a;
  border-radius: 3px;
}

/* 隐藏 el-divider 的默认 margin */
:deep(.el-divider) {
  margin: 16px 0 12px;
}
</style>
