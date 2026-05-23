<template>
  <div class="asset-profile-page">
    <h2>资产画像</h2>

    <!-- ═══════════ 统计卡片 ═══════════ -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(99,102,241,0.12);color:#6366f1">
            <el-icon><Link /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.域名数量 }}</div>
            <div class="stat-label">域名数量</div>
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(16,185,129,0.12);color:#10b981">
            <el-icon><Monitor /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.公网IP端口数量 }}</div>
            <div class="stat-label">公网IP+端口</div>
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(245,158,11,0.12);color:#f59e0b">
            <el-icon><Cloudy /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.虚拟机数量 }}</div>
            <div class="stat-label">虚拟机数量</div>
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(239,68,68,0.12);color:#ef4444">
            <el-icon><Connection /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.虚拟机IP端口数量 }}</div>
            <div class="stat-label">VM IP+端口</div>
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(139,92,246,0.12);color:#8b5cf6">
            <el-icon><Grid /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.vlan数量 }}</div>
            <div class="stat-label">VLAN 数量</div>
          </div>
        </div>
      </el-col>
      <el-col :span="4">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(6,182,212,0.12);color:#06b6d4">
            <el-icon><FolderOpened /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.文件夹数量 }}</div>
            <div class="stat-label">文件夹数量</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ═══════════ 搜索与筛选 ═══════════ -->
    <div class="toolbar">
      <el-input
        v-model="search"
        placeholder="搜索域名、IP、虚拟机名称、MAC地址..."
        clearable
        @keyup.enter="fetchData"
        @clear="fetchData"
        class="search-input"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="filterSource" clearable filterable placeholder="来源" style="width:200px" @change="page=1;fetchData()">
        <el-option v-for="s in sourceNames" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="filterStatus" clearable placeholder="状态类型" style="width:110px" @change="page=1;fetchData()">
        <el-option label="在线" value="up" />
        <el-option label="离线" value="down" />
        <el-option label="禁用" value="user-down" />
      </el-select>
      <el-select v-model="filterNetwork" clearable filterable placeholder="网络名称" style="width:160px" @change="page=1;fetchData()">
        <el-option v-for="n in networkNames" :key="n" :label="n" :value="n" />
      </el-select>
      <span class="total-hint">共 {{ total }} 条资产记录</span>
    </div>

    <!-- ═══════════ 数据表格 ═══════════ -->
    <el-table :data="items" v-loading="loading" stripe style="width:100%" @sort-change="handleSort">
      <template #empty>
        <el-empty description="暂无资产画像数据，请先对各数据源执行扫描" :image-size="80" />
      </template>

      <el-table-column type="index" width="50" label="#" />

      <el-table-column prop="域名" label="域名" min-width="180" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="来源" label="来源" width="260" sortable="custom">
        <template #default="{ row }">
          <span style="display:flex;flex-wrap:wrap;gap:2px;">
            <template v-for="s in (row.来源 || '').split(',').filter(Boolean)" :key="s">
              <el-tag v-if="s==='ZDNS'" type="primary" size="small">ZDNS</el-tag>
              <el-tag v-else-if="s==='F5'" type="success" size="small">F5</el-tag>
              <el-tag v-else-if="s==='vCenter'" type="warning" size="small">vCenter</el-tag>
              <el-tag v-else-if="s==='Switch'" type="danger" size="small">Switch</el-tag>
              <el-tag v-else size="small">{{ s }}</el-tag>
            </template>
          </span>
          <span v-if="!row.来源" style="color:#c0c4cc;">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="公网IP" label="公网IP" width="200" sortable="custom" />

      <el-table-column prop="端口" label="端口" width="80" sortable="custom">
        <template #default="{ row }">{{ row.端口 || '-' }}</template>
      </el-table-column>

      <el-table-column prop="内网服务IP" label="内网服务IP" width="150" sortable="custom" />

      <el-table-column prop="内网端口" label="内网端口" width="90" sortable="custom">
        <template #default="{ row }">{{ row.内网端口 || '-' }}</template>
      </el-table-column>

      <el-table-column prop="状态" label="状态" width="80" sortable="custom" align="center">
        <template #default="{ row }">
          <span v-if="row.状态" class="status-dot" :class="statusClass(row.状态)" :title="row.状态">
            {{ statusLabel(row.状态) }}
          </span>
          <span v-else class="status-na">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="虚拟机名称" label="虚拟机名称" min-width="180" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="IP地址" label="IP地址" width="150" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="MAC地址" label="MAC地址" width="170" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="网络" label="网络" width="120" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="VLAN" label="VLAN" width="100" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="文件夹" label="文件夹" min-width="140" sortable="custom" show-overflow-tooltip />
    </el-table>

    <!-- ═══════════ 分页 ═══════════ -->
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getAssetProfile } from '@/api/asset'

const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const search = ref('')

const stats = reactive({
  域名数量: 0,
  公网IP端口数量: 0,
  虚拟机数量: 0,
  虚拟机IP端口数量: 0,
  vlan数量: 0,
  文件夹数量: 0,
})

const sortBy = ref('')
const sortDir = ref('asc')
const filterStatus = ref('')
const filterNetwork = ref('')
const filterSource = ref('')
const networkNames = ref([])
const sourceNames = ref([])

function statusClass(state) {
  const s = (state || '').toLowerCase()
  if (s === 'up') return 'dot-up'
  if (s === 'down') return 'dot-down'
  if (s.startsWith('user')) return 'dot-user'
  return 'dot-unknown'
}

function statusLabel(state) {
  const s = (state || '').toLowerCase()
  if (s === 'up') return '在线'
  if (s === 'down') return '离线'
  if (s === 'user-down') return '禁用'
  return state || '-'
}

function handleSort({ prop, order }) {
  sortBy.value = prop || ''
  sortDir.value = order === 'descending' ? 'desc' : 'asc'
  page.value = 1
  fetchData()
}

async function fetchData() {
  loading.value = true
  try {
    const data = await getAssetProfile({
      page: page.value,
      size: size.value,
      search: search.value,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
      status: filterStatus.value,
      network: filterNetwork.value,
      source: filterSource.value,
    })
    items.value = data.rows
    total.value = data.total
    Object.assign(stats, data.stats)
    if (data.network_names) networkNames.value = data.network_names
    if (data.source_names) sourceNames.value = data.source_names
  } catch {
    /* handled */
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.asset-profile-page h2 {
  margin: 0 0 20px;
  font-size: 22px;
  font-weight: 700;
}

/* ── 统计卡片 ── */
.stats-row {
  margin-bottom: 20px;
}

.stat-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  transition: box-shadow 0.2s;
}

.stat-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.stat-info {
  min-width: 0;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.2;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}

/* ── 工具栏 ── */
.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  background: var(--color-bg-card);
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.search-input {
  width: 400px;
}

.total-hint {
  font-size: 13px;
  color: var(--color-text-muted);
}

/* ── 分页 ── */
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* ── 状态指示器 ── */
.status-dot {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}
.dot-up {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.08);
}
.dot-down {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
}
.dot-user {
  color: #909399;
  background: rgba(144, 147, 153, 0.08);
}
.dot-unknown {
  color: #c0c4cc;
}
.status-na {
  color: var(--color-text-muted);
  font-size: 13px;
}
</style>
