<template>
  <div class="asset-profile-page">
    <h2>资产画像</h2>

    <!-- ═══════════ 统计卡片 ═══════════ -->
    <el-row :gutter="12" class="stats-row">
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(99,102,241,0.12);color:#6366f1">
            <el-icon><Link /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.zdnsDomains }}</div>
            <div class="stat-label">ZDNS 域名</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(16,185,129,0.12);color:#10b981">
            <el-icon><Monitor /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.f5Domains }}</div>
            <div class="stat-label">F5 域名</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(6,182,212,0.12);color:#06b6d4">
            <el-icon><Share /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.pubIPPorts }}</div>
            <div class="stat-label">公网IP:端口</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(239,68,68,0.12);color:#ef4444">
            <el-icon><Connection /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.intIPPorts }}</div>
            <div class="stat-label">内网服务</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(245,158,11,0.12);color:#f59e0b">
            <el-icon><Cloudy /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.vmNames }}</div>
            <div class="stat-label">虚拟机</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(234,179,8,0.12);color:#ca8a04">
            <el-icon><Tickets /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.vmIPs }}</div>
            <div class="stat-label">VM IP</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(139,92,246,0.12);color:#8b5cf6">
            <el-icon><Grid /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.vlans }}</div>
            <div class="stat-label">VLAN</div>
          </div>
        </div>
      </el-col>
      <el-col :span="3">
        <div class="stat-card">
          <div class="stat-icon" style="background:rgba(236,72,153,0.12);color:#db2777">
            <el-icon><FolderOpened /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ ds.folders }}</div>
            <div class="stat-label">文件夹</div>
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
      <el-select v-model="filterStatus" clearable placeholder="状态" style="width:110px" @change="page=1;fetchData()">
        <el-option label="在线" value="up" />
        <el-option label="离线" value="down" />
        <el-option label="禁用" value="user-down" />
      </el-select>
      <el-select v-model="filterNetwork" clearable filterable placeholder="网络名称" style="width:160px" @change="page=1;fetchData()">
        <el-option v-for="n in networkNames" :key="n" :label="n" :value="n" />
      </el-select>
      <span class="total-hint">共 {{ total }} 条</span>
    </div>

    <!-- ═══════════ 数据表格 ═══════════ -->
    <el-table :data="pagedItems" v-loading="loading" stripe style="width:100%" @sort-change="handleSort">
      <template #empty>
        <el-empty description="暂无资产画像数据，请先对各数据源执行扫描" :image-size="80" />
      </template>

      <el-table-column type="index" width="45" label="#" />

      <el-table-column prop="域名" label="域名" min-width="160" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="来源" label="来源" width="230" sortable="custom">
        <template #default="{ row }">
          <span style="display:flex;flex-wrap:wrap;gap:2px;">
            <template v-for="s in (row.来源 || '').split(',').filter(Boolean)" :key="s">
              <el-tag v-if="s==='ZDNS'" type="primary" size="small">ZDNS</el-tag>
              <el-tag v-else-if="s==='F5'" type="success" size="small">F5</el-tag>
              <el-tag v-else-if="s==='vCenter'" type="warning" size="small">vCenter</el-tag>
              <el-tag v-else-if="s==='Switch'" class="switch-tag" size="small">Switch</el-tag>
            </template>
          </span>
          <span v-if="!row.来源" style="color:#c0c4cc;">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="公网IP端口" label="公网IP:端口" min-width="210" sortable="custom" show-overflow-tooltip>
        <template #default="{ row }">{{ row.公网IP端口 || '-' }}</template>
      </el-table-column>

      <el-table-column prop="内网服务文本" label="内网服务 (IP:端口 / 状态)" min-width="280" sortable="custom" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.内网服务 && row.内网服务.length" class="int-svc-list">
            <span v-for="svc in row.内网服务" :key="svc.ipp" class="int-svc-item">
              <span class="int-svc-ipp">{{ svc.ipp }}</span>
              <span v-if="svc.st" class="svc-status-tag" :class="svcStatusClass(svc.st)">{{ svc.st }}</span>
            </span>
          </span>
          <span v-else style="color:#c0c4cc;">-</span>
        </template>
      </el-table-column>

      <el-table-column prop="虚拟机名称" label="虚拟机名称" min-width="160" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="IP地址" label="IP地址" min-width="160" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="MAC地址" label="MAC地址" min-width="160" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="网络" label="网络" width="120" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="VLAN" label="VLAN" width="90" sortable="custom" show-overflow-tooltip />

      <el-table-column prop="文件夹" label="文件夹" min-width="140" sortable="custom" show-overflow-tooltip />
    </el-table>

    <!-- ═══════════ 分页 ═══════════ -->
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getAssetProfile } from '@/api/asset'

const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const search = ref('')

const rawRows = ref([])

// ── 前端去重统计（从原始行计算） ──
const ds = computed(() => {
  const zdnsDomains = new Set()
  const f5Domains = new Set()
  const pubIPPorts = new Set()
  const intIPPorts = new Set()
  const vmNames = new Set()
  const vmIPs = new Set()
  const vlans = new Set()
  const folders = new Set()
  for (const r of rawRows.value) {
    const src = r['来源'] || ''
    if (src.includes('ZDNS')) zdnsDomains.add(r['域名'])
    if (src.includes('F5')) f5Domains.add(r['域名'])
    if (r['公网IP']) pubIPPorts.add(r['端口'] ? `${r['公网IP']}:${r['端口']}` : r['公网IP'])
    if (r['内网服务IP']) intIPPorts.add(r['内网端口'] ? `${r['内网服务IP']}:${r['内网端口']}` : r['内网服务IP'])
    if (r['虚拟机名称']) {
      for (const v of r['虚拟机名称'].split(',')) { const t = v.trim(); if (t) vmNames.add(t) }
    }
    if (r['IP地址']) {
      for (const ip of r['IP地址'].split(',')) { const t = ip.trim(); if (t) vmIPs.add(t) }
    }
    if (r['VLAN']) {
      for (const v of r['VLAN'].split(',')) { const t = v.trim(); if (t) vlans.add(t) }
    }
    if (r['文件夹']) folders.add(r['文件夹'])
  }
  return {
    zdnsDomains: zdnsDomains.size,
    f5Domains: f5Domains.size,
    pubIPPorts: pubIPPorts.size,
    intIPPorts: intIPPorts.size,
    vmNames: vmNames.size,
    vmIPs: vmIPs.size,
    vlans: vlans.size,
    folders: folders.size,
  }
})

const sortBy = ref('域名')
const sortDir = ref('asc')
const filterStatus = ref('')
const filterNetwork = ref('')
const filterSource = ref('')
const networkNames = ref([])
const sourceNames = ref([])

// ── 状态值翻译 ──
const STATUS_MAP = {
  up: '在线',
  down: '离线',
  'user-down': '禁用',
  'user-up': '启用',
}

function _tranStatus(s) {
  return STATUS_MAP[s] || s
}

// ── 辅助：拆分 CSV → Set ──
function _csvToSet(csv) {
  const set = new Set()
  if (!csv) return set
  for (const v of csv.split(',')) {
    const t = v.trim()
    if (t) set.add(t)
  }
  return set
}

// ── 聚合：按 域名 + 公网IP:端口（Pool）分组 ──
function aggregateByPool(rows) {
  const map = new Map()
  for (const r of rows) {
    const pubKey = r['公网IP'] ? `${r['公网IP']}:${r['端口'] || ''}` : ''
    const groupKey = pubKey ? `${r['域名']}||${pubKey}` : r['域名']

    if (!map.has(groupKey)) {
      map.set(groupKey, {
        域名: r['域名'],
        公网IP端口: pubKey || '',
        sources: new Set(),
        // internalServices: "IP:Port" → Set of translated statuses
        internalServices: new Map(),
        vmNames: new Set(),
        ipList: new Set(),
        macList: new Set(),
        nets: new Set(),
        vlans: new Set(),
        folders: new Set(),
      })
    }
    const e = map.get(groupKey)

    // 来源（域名级合并）
    for (const s of (r['来源'] || '').split(',').filter(Boolean)) e.sources.add(s)

    // 内网 IP:Port + 状态
    if (r['内网服务IP']) {
      const intKey = r['内网端口'] ? `${r['内网服务IP']}:${r['内网端口']}` : r['内网服务IP']
      if (!e.internalServices.has(intKey)) {
        e.internalServices.set(intKey, new Set())
      }
      if (r['状态']) {
        e.internalServices.get(intKey).add(_tranStatus(r['状态']))
      }
    }

    // 虚拟机名称
    if (r['虚拟机名称']) {
      for (const v of r['虚拟机名称'].split(',')) { const t = v.trim(); if (t) e.vmNames.add(t) }
    }

    // IP 地址 / MAC / 网络 / VLAN / 文件夹
    for (const ip of _csvToSet(r['IP地址'])) e.ipList.add(ip)
    for (const mac of _csvToSet(r['MAC地址'])) e.macList.add(mac)
    for (const n of _csvToSet(r['网络'])) e.nets.add(n)
    if (r['VLAN']) e.vlans.add(r['VLAN'])
    if (r['文件夹']) e.folders.add(r['文件夹'])
  }

  return [...map.values()].map(e => ({
    域名: e.域名,
    来源: [...e.sources].sort().join(','),
    公网IP端口: e.公网IP端口,
    内网服务: [...e.internalServices.entries()]
      .map(([ipp, stSet]) => {
        const st = [...stSet].sort().join('/')
        return { ipp, st }
      })
      .sort((a, b) => a.ipp.localeCompare(b.ipp)),
    内网服务文本: [...e.internalServices.entries()].map(([ipp, stSet]) => `${ipp} ${[...stSet].sort().join('/')}`).join(', '),
    虚拟机名称: [...e.vmNames].sort().join(', '),
    IP地址: [...e.ipList].sort().join(', '),
    MAC地址: [...e.macList].sort().join(', '),
    网络: [...e.nets].sort().join(', '),
    VLAN: [...e.vlans].sort().join(', '),
    文件夹: [...e.folders].sort().join(', '),
  }))
}

const aggregatedAll = ref([])

// ── 前端排序 ──
const sortedAggregated = computed(() => {
  const list = [...aggregatedAll.value]
  if (!sortBy.value) {
    return list.sort((a, b) => a['域名'].localeCompare(b['域名']))
  }
  const key = sortBy.value
  const rev = sortDir.value === 'desc'
  return list.sort((a, b) => {
    const va = (a[key] || '').toString().toLowerCase()
    const vb = (b[key] || '').toString().toLowerCase()
    return rev ? vb.localeCompare(va) : va.localeCompare(vb)
  })
})

// ── 前端分页 ──
const pagedItems = computed(() => {
  const start = (page.value - 1) * size.value
  return sortedAggregated.value.slice(start, start + size.value)
})

function handleSort({ prop, order }) {
  sortBy.value = prop || ''
  sortDir.value = order === 'descending' ? 'desc' : 'asc'
  page.value = 1
}

function svcStatusClass(st) {
  if (st.includes('在线')) return 'svc-up'
  if (st.includes('离线')) return 'svc-down'
  if (st.includes('禁用')) return 'svc-user'
  return 'svc-other'
}

function onPageChange(p) {
  page.value = p
}

async function fetchData() {
  loading.value = true
  try {
    const data = await getAssetProfile({
      page: 1,
      size: 10000,
      search: search.value,
      sort_by: '',
      sort_dir: 'asc',
      status: filterStatus.value,
      network: filterNetwork.value,
      source: filterSource.value,
    })
    rawRows.value = data.rows
    aggregatedAll.value = aggregateByPool(data.rows)
    total.value = aggregatedAll.value.length
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
  white-space: nowrap;
}

/* ── 分页 ── */
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* ── Switch 标签（与其他 tag 同风格，柔和青色调） ── */
:deep(.switch-tag) {
  background: rgba(6, 182, 212, 0.1);
  border-color: rgba(6, 182, 212, 0.25);
  color: #0891b2;
}

/* ── 内网服务列表 ── */
.int-svc-list {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 6px;
  line-height: 1.8;
}

.int-svc-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.int-svc-ipp {
  font-variant-numeric: tabular-nums;
}

.svc-status-tag {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  padding: 0 4px;
  border-radius: 3px;
  line-height: 1.5;
}

.svc-up {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.08);
}

.svc-down {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.08);
}

.svc-user {
  color: #909399;
  background: rgba(144, 147, 153, 0.08);
}

.svc-other {
  color: #a1a5b7;
  background: rgba(161, 165, 183, 0.06);
}
</style>
