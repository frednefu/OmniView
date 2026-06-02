<template>
  <div class="monitor-page">
    <div class="page-header">
      <div class="header-left">
        <h2>扫描监控</h2>
        <span v-if="runningCount > 0" class="running-badge">
          <span class="pulse-dot"></span>
          {{ runningCount }} 个任务运行中
        </span>
      </div>
      <div class="header-right">
        <el-button
          v-if="items.length > 0"
          size="small"
          type="danger"
          @click="clearAll"
          :loading="clearingAll"
        >
          <el-icon><Delete /></el-icon> 全部删除 ({{ items.length }})
        </el-button>
        <el-switch
          v-model="autoRefresh"
          active-text="自动刷新"
          size="small"
        />
        <el-button text @click="fetchAll" :loading="loading">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.source_type" placeholder="全部数据源" clearable style="width:140px" @change="fetchAll">
        <el-option label="交换机" value="switch" />
        <el-option label="vCenter" value="vcenter" />
        <el-option label="F5" value="f5" />
        <el-option label="ZDNS" value="zdns" />
        <el-option label="IP扫描" value="zdns_ip" />
        <el-option label="椒图" value="qax" />
        <el-option label="鼎甲备份" value="dingjia" />
      </el-select>
      <el-select v-model="filters.status" placeholder="全部状态" clearable style="width:120px" @change="fetchAll">
        <el-option label="扫描中" value="running" />
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
      </el-select>
    </div>

    <div v-if="items.length === 0 && !loading" class="empty-state">
      <el-empty description="暂无扫描任务" :image-size="100" />
    </div>

    <div v-else class="card-grid">
      <div
        v-for="item in items"
        :key="item.id"
        class="task-card"
        :class="[`status-${item.status}`, { expanded: expandedId === item.id }]"
      >
        <div class="card-main" @click="toggleExpand(item)">
          <div class="card-top">
            <div class="card-source">
              <el-tag :color="sourceColor(item.source_type)" size="small" effect="dark">
                {{ sourceLabel(item.source_type) }}
              </el-tag>
              <span class="device-name">{{ item.source_name }}</span>
            </div>
            <div class="card-meta">
              <span v-if="item.worker_name" class="worker-name" :title="'执行节点: ' + item.worker_name">
                <el-icon><Monitor /></el-icon> {{ item.worker_name }}
              </span>
              <span v-if="item.status === 'running'" class="elapsed">
                <span class="pulse-dot" :class="{ 'pulse-slow': isQueued(item) }"></span>
                {{ elapsedTime(item.started_at) }}
              </span>
              <span v-else-if="item.duration_seconds != null" class="duration">
                {{ item.duration_seconds }}s
              </span>
              <el-tag
                :type="statusTag(item.status)"
                size="small"
                effect="plain"
              >
                {{ statusLabel(item) }}
              </el-tag>
            </div>
          </div>

          <div v-if="item.status === 'running'" class="card-progress">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :class="{ 'progress-queued': isQueued(item) }"
                :style="{ width: Math.max(item.progress_pct || 0, isQueued(item) ? 2 : 0) + '%' }"
              ></div>
            </div>
            <span class="progress-text">{{ Math.max(item.progress_pct || 0, isQueued(item) ? 0 : 0) }}%</span>
          </div>

          <div class="card-step">
            <el-icon v-if="item.status === 'running' && !isQueued(item)" class="spin-icon"><Loading /></el-icon>
            <el-icon v-else-if="item.status === 'running'" class="icon-queued"><Clock /></el-icon>
            <el-icon v-else-if="item.status === 'success'" class="icon-success"><CircleCheckFilled /></el-icon>
            <el-icon v-else class="icon-failed"><CircleCloseFilled /></el-icon>
            <span>{{ item.current_step || (item.status === 'success' ? '扫描完成' : item.status === 'failed' ? '扫描失败' : '等待中...') }}</span>
          </div>

          <div class="card-actions" @click.stop>
            <el-button v-if="item.status === 'running'" size="small" type="warning" plain @click="cancelScan(item)" :loading="cancellingId === item.id">
              取消扫描
            </el-button>
            <el-button size="small" type="danger" plain @click="deleteRecord(item)" :loading="deletingId === item.id">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </div>
        </div>

        <transition name="expand">
          <div v-if="expandedId === item.id" class="card-detail">
            <div class="detail-tabs">
              <span
                class="tab-btn"
                :class="{ active: detailTab === 'steps' }"
                @click="detailTab = 'steps'"
              >步骤</span>
              <span
                class="tab-btn"
                :class="{ active: detailTab === 'terminal' }"
                @click="switchToTerminal(item)"
              >终端</span>
            </div>

            <!-- 步骤列表 -->
            <div v-if="detailTab === 'steps'" class="detail-body">
              <div v-if="stepsLoading" class="steps-loading">
                <el-icon class="spin-icon"><Loading /></el-icon> 加载步骤...
              </div>
              <div v-else-if="steps.length === 0" class="steps-empty">暂无步骤记录</div>
              <div v-else class="step-list">
                <div
                  v-for="step in sortedSteps"
                  :key="step.id"
                  class="step-item"
                  :class="`step-${step.status}`"
                >
                  <div class="step-indicator">
                    <el-icon v-if="step.status === 'running'" class="spin-icon"><Loading /></el-icon>
                    <el-icon v-else-if="step.status === 'success'"><CircleCheckFilled /></el-icon>
                    <el-icon v-else-if="step.status === 'failed'"><CircleCloseFilled /></el-icon>
                    <el-icon v-else><Clock /></el-icon>
                  </div>
                  <div class="step-body">
                    <div class="step-name">{{ step.step_name }}</div>
                    <div class="step-meta">
                      <span v-if="step.items_total > 0">{{ step.items_processed }}/{{ step.items_total }} 条</span>
                      <span v-if="step.error_message" class="step-error">{{ step.error_message }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 终端输出 -->
            <div v-else class="detail-body">
              <div class="terminal-window" ref="terminalRef">
                <div v-if="!terminalOutput" class="terminal-empty">
                  暂无输出，扫描开始后将实时显示...
                </div>
                <pre v-else class="terminal-text">{{ terminalOutput }}</pre>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { getScanLogs, getScanSteps, getScanOutput, deleteScanLog, clearScanLogs } from '@/api/scanLogs'
import api from '@/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'

const items = ref([])
const loading = ref(false)
const steps = ref([])
const stepsLoading = ref(false)
const expandedId = ref(null)
const cancellingId = ref(null)
const deletingId = ref(null)
const autoRefresh = ref(true)
const clearingAll = ref(false)
const detailTab = ref('steps')
const terminalOutput = ref('')
const terminalRef = ref(null)

let refreshTimer = null
let terminalTimer = null

const filters = reactive({ source_type: '', status: 'running' })

const runningCount = computed(() => items.value.filter(i => i.status === 'running').length)

const sortedSteps = computed(() => [...steps.value].sort((a, b) => a.step_order - b.step_order))

function isQueued(item) {
  const cs = item.current_step || ''
  return cs.includes('队列') || cs.includes('等待')
}

function sourceColor(type) {
  const map = { switch: '#06b6d4', vcenter: '#f59e0b', f5: '#10b981', zdns: '#6366f1', zdns_ip: '#8b5cf6', qax: '#ef4444', dingjia: '#ec4899' }
  return map[type] || '#94a3b8'
}

function sourceLabel(type) {
  const map = { switch: '交换机', vcenter: 'vCenter', f5: 'F5', zdns: 'ZDNS', zdns_ip: 'IP扫描', qax: '椒图', dingjia: '鼎甲备份' }
  return map[type] || type
}

function statusTag(status) {
  const map = { running: 'warning', success: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function statusLabel(item) {
  if (item.status !== 'running') {
    const map = { success: '成功', failed: '失败' }
    return map[item.status] || item.status
  }
  const cs = item.current_step || ''
  if (cs.includes('队列') || cs.includes('等待 Worker')) return '排队中'
  return '扫描中'
}

function elapsedTime(startedAt) {
  if (!startedAt) return ''
  const diff = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

// ── 数据获取（纯手动刷新，不自动轮询，不含 WebSocket）──

async function fetchAll() {
  loading.value = true
  try {
    const params = { page: 1, size: 50 }
    if (filters.source_type) params.source_type = filters.source_type
    if (filters.status) params.status = filters.status
    const data = await getScanLogs(params)
    items.value = data.items || []
  } catch { /* handled */ }
  finally { loading.value = false }
}

// ── 展开 / 步骤 / 终端 ──

async function toggleExpand(item) {
  if (expandedId.value === item.id) {
    expandedId.value = null
    stopTerminalPoll()
    return
  }
  expandedId.value = item.id
  detailTab.value = 'steps'
  await fetchSteps(item.id)
}

async function switchToTerminal(item) {
  detailTab.value = 'terminal'
  await fetchTerminal(item.id)
  startTerminalPoll(item.id)
}

async function fetchSteps(logId) {
  stepsLoading.value = true
  steps.value = []
  try {
    const data = await getScanSteps(logId)
    steps.value = data || []
  } catch { /* handled */ }
  finally { stepsLoading.value = false }
}

async function fetchTerminal(logId) {
  try {
    const data = await getScanOutput(logId)
    const raw = data.log_output || ''
    terminalOutput.value = raw.length > 100000 ? '...(日志过长，仅显示最后 100KB)\n' + raw.slice(-100000) : raw
    await nextTick()
    scrollTerminal()
  } catch { /* handled */ }
}

function scrollTerminal() {
  if (terminalRef.value) {
    terminalRef.value.scrollTop = terminalRef.value.scrollHeight
  }
}

function startTerminalPoll(logId) {
  stopTerminalPoll()
  terminalTimer = setInterval(() => { fetchTerminal(logId) }, 2000)
}

function stopTerminalPoll() {
  if (terminalTimer) {
    clearInterval(terminalTimer)
    terminalTimer = null
  }
}

// ── 操作按钮 ──

async function cancelScan(item) {
  try {
    await ElMessageBox.confirm(`确定要取消 ${item.source_name} 的扫描吗？`, '确认取消', {
      type: 'warning', confirmButtonText: '确定取消',
    })
  } catch { return }

  cancellingId.value = item.id
  try {
    const type = item.source_type; const id = item.source_id
    if (type === 'switch') await api.post(`/switches/${id}/cancel-scan`)
    else if (type === 'vcenter') await api.post(`/vcenters/${id}/cancel-scan`)
    else if (type === 'f5') await api.post(`/f5/${id}/cancel-scan`)
    else if (type === 'zdns') await api.post(`/zdns/${id}/cancel-scan`)
    else if (type === 'zdns_ip') await api.post(`/zdns/${id}/cancel-ip-scan`)
    else if (type === 'qax') await api.post(`/qax/${id}/cancel-scan`)
    ElMessage.success('已取消扫描')
    fetchAll()
  } catch { /* handled */ }
  finally { cancellingId.value = null }
}

async function deleteRecord(item) {
  try {
    await ElMessageBox.confirm(`确定要删除 ${item.source_name} 的扫描记录吗？`, '确认删除', {
      type: 'warning', confirmButtonText: '确定删除',
    })
  } catch { return }

  deletingId.value = item.id
  try {
    await deleteScanLog(item.id)
    ElMessage.success('已删除扫描记录')
    if (expandedId.value === item.id) { expandedId.value = null; stopTerminalPoll() }
    fetchAll()
  } catch { /* handled */ }
  finally { deletingId.value = null }
}

async function clearAll() {
  try {
    await ElMessageBox.confirm(
      `确定要删除全部 ${items.value.length} 条扫描记录吗？此操作不可撤销。`,
      '确认全部删除',
      { type: 'warning', confirmButtonText: '确定删除' }
    )
  } catch { return }

  clearingAll.value = true
  try {
    const res = await clearScanLogs(null, null)
    ElMessage.success(res.message || '已清除')
    fetchAll()
  } catch { /* handled */ }
  finally { clearingAll.value = false }
}

// ── 自动刷新轮询 ──

function startPolling() {
  stopPolling()
  refreshTimer = setInterval(() => { fetchAll() }, 5000)
}

function stopPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

watch(autoRefresh, (val) => {
  if (val) { startPolling() } else { stopPolling() }
})

onMounted(() => {
  fetchAll()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  stopTerminalPoll()
})

if (import.meta.hot) {
  import.meta.hot.decline()
}
</script>

<style scoped>
.monitor-page h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.running-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-color-warning);
  background: rgba(230, 162, 60, 0.1);
  padding: 4px 12px;
  border-radius: 20px;
  font-weight: 500;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-warning);
  display: inline-block;
  animation: pulse 1.5s ease-in-out infinite;
}

.pulse-slow {
  background: var(--color-text-muted);
  animation: pulse 3s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.4); }
}

.filter-bar {
  margin-bottom: 20px;
  display: flex;
  gap: 12px;
}

.empty-state {
  padding: 80px 0;
}

.card-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  overflow: hidden;
  transition: all 0.2s;
  border-left: 4px solid transparent;
}

.task-card.status-running {
  border-left-color: var(--el-color-warning);
}

.task-card.status-success {
  border-left-color: var(--el-color-success);
}

.task-card.status-failed {
  border-left-color: var(--el-color-danger);
}

.task-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.task-card.expanded {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.card-main {
  padding: 16px 20px;
  cursor: pointer;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.card-source {
  display: flex;
  align-items: center;
  gap: 10px;
}

.device-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.worker-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
  background: var(--color-bg);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
}

.elapsed {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-variant-numeric: tabular-nums;
}

.card-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--color-bg);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--el-color-warning), var(--el-color-primary));
  border-radius: 3px;
  transition: width 0.6s ease;
}

.progress-queued {
  background: var(--color-text-muted);
  animation: shimmer 2s ease-in-out infinite;
}

@keyframes shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.progress-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  min-width: 36px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.card-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.card-actions {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.icon-success { color: var(--el-color-success); }
.icon-failed { color: var(--el-color-danger); }
.icon-queued { color: var(--color-text-muted); }

/* ── 展开详情区 ── */
.card-detail {
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
}

.detail-tabs {
  display: flex;
  border-bottom: 1px solid var(--color-border);
}

.tab-btn {
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  user-select: none;
}

.tab-btn:hover {
  color: var(--color-text-secondary);
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.detail-body {
  padding: 12px 20px 16px;
  min-height: 60px;
}

/* ── 步骤列表 ── */
.steps-loading, .steps-empty {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 8px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
}

.step-indicator {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.step-running .step-indicator { color: var(--el-color-warning); }
.step-success .step-indicator { color: var(--el-color-success); }
.step-failed .step-indicator { color: var(--el-color-danger); }
.step-pending .step-indicator { color: var(--color-text-muted); }

.step-body {
  flex: 1;
}

.step-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.step-meta {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

.step-error {
  color: var(--el-color-danger);
  margin-left: 8px;
}

/* ── 终端窗口 ── */
.terminal-window {
  background: #1a1b2e;
  border-radius: 8px;
  padding: 14px 16px;
  max-height: 400px;
  overflow-y: auto;
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
}

.terminal-window::-webkit-scrollbar {
  width: 6px;
}

.terminal-window::-webkit-scrollbar-track {
  background: transparent;
}

.terminal-window::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.12);
  border-radius: 3px;
}

.terminal-empty {
  color: rgba(255,255,255,0.3);
  font-size: 13px;
}

.terminal-text {
  margin: 0;
  color: #a8d8a8;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── 展开动画 ── */
.expand-enter-active, .expand-leave-active {
  transition: all 0.25s ease;
  max-height: 600px;
}

.expand-enter-from, .expand-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
