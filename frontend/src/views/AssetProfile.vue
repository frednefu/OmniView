<template>
  <div class="asset-profile-page">
    <!-- ═══════════ 顶部栏 ═══════════ -->
    <div class="top-bar">
      <h2>资产画像</h2>
      <div class="stats-ribbon">
        <span class="stat-chip" :class="{ active: selectedDomain }" @click="selectedDomain=null">
          域名 <strong>{{ realDomains.length }}</strong>
        </span>
        <span class="stat-sep">·</span>
        <span class="stat-chip">公网入口 <strong>{{ totalVIPs }}</strong></span>
        <span class="stat-sep">·</span>
        <span class="stat-chip">后端服务 <strong>{{ totalMembers }}</strong></span>
        <span class="stat-sep">·</span>
        <span class="stat-chip">虚拟机 <strong>{{ totalVMs }}</strong></span>
        <span class="stat-sep">·</span>
        <span class="stat-chip">VLAN <strong>{{ totalVLANs }}</strong></span>
        <span class="stat-sep">·</span>
        <span class="stat-chip">文件夹 <strong>{{ totalFolders }}</strong></span>
        <span v-if="pseudoDomains.length" class="stat-sep">·</span>
        <span v-if="pseudoDomains.length" class="stat-chip pseudo">未关联 <strong>{{ pseudoDomains.length }}</strong></span>
      </div>
      <el-button v-if="authStore?.isAdmin" @click="exportExcel" :loading="exporting" size="small" class="export-btn">
        <el-icon><Download /></el-icon>导出
      </el-button>
    </div>

    <!-- ═══════════ 主体 ═══════════ -->
    <div class="main-area">
      <!-- 左侧域名列表 -->
      <div class="domain-panel">
        <div class="panel-search">
          <el-input v-model="search" placeholder="搜索域名..." clearable size="small"
            @input="onSearchInput">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
        <div class="panel-filters">
          <el-checkbox-button v-model="showZDNS" size="small" @change="applyFilters">ZDNS</el-checkbox-button>
          <el-checkbox-button v-model="showF5" size="small" @change="applyFilters">F5</el-checkbox-button>
          <el-checkbox-button v-model="showVCenter" size="small" @change="applyFilters">vCenter</el-checkbox-button>
          <el-checkbox-button v-model="showSwitch" size="small" @change="applyFilters">交换机</el-checkbox-button>
          <el-checkbox-button v-model="showQAX" size="small" @change="applyFilters">椒图</el-checkbox-button>
        </div>

        <!-- 已关联域名 -->
        <div class="domain-list">
          <div class="list-section-label">已关联域名 <span class="count">({{ filteredDomains.length }})</span></div>
          <div
            v-for="d in filteredDomains"
            :key="d.domain"
            class="domain-item"
            :class="{ selected: selectedDomain?.domain === d.domain }"
            @click="selectDomain(d)"
          >
            <div class="domain-name">{{ d.domain }}</div>
            <div class="domain-meta">
              <span class="source-dots">
                <span v-if="d.sources.includes('ZDNS')" class="dot zdns">Z</span>
                <span v-if="d.sources.includes('F5')" class="dot f5">F</span>
                <span v-if="d.sources.includes('vCenter')" class="dot vc">V</span>
                <span v-if="d.sources.includes('Switch')" class="dot sw">S</span>
                <span v-if="d.sources.includes('椒图')" class="dot qax">Q</span>
              </span>
              <span class="domain-counts">
                <span v-if="d.vipCount">{{ d.vipCount }} 入口</span>
                <span v-if="d.memberCount"> · {{ d.memberCount }} 后端</span>
                <span v-if="d.vmCount"> · {{ d.vmCount }} VM</span>
              </span>
            </div>
          </div>
          <div v-if="filteredDomains.length === 0" class="list-empty">无匹配域名</div>
        </div>

        <!-- 未关联资产 -->
        <div v-if="pseudoDomains.length && showPseudo" class="pseudo-section">
          <div class="pseudo-header" @click="showPseudo = false">
            <el-icon><ArrowDown /></el-icon>
            未关联域名的资产 ({{ pseudoDomains.length }})
          </div>
          <div
            v-for="d in pseudoDomains"
            :key="d.domain"
            class="domain-item pseudo-item"
            :class="{ selected: selectedDomain?.domain === d.domain }"
            @click="selectDomain(d)"
          >
            <div class="domain-name">{{ d.domain }}</div>
            <div class="domain-meta">
              <el-tag size="small" type="info">VS直连</el-tag>
              <span class="domain-counts">
                <span v-if="d.memberCount">{{ d.memberCount }} 后端</span>
                <span v-if="d.vmCount"> · {{ d.vmCount }} VM</span>
              </span>
            </div>
          </div>
        </div>
        <div v-if="pseudoDomains.length && !showPseudo" class="pseudo-toggle" @click="showPseudo = true">
          <el-icon><ArrowRight /></el-icon>
          未关联域名的资产 ({{ pseudoDomains.length }})
        </div>
      </div>

      <!-- ═══════════ 右侧资产链路 ═══════════ -->
      <div class="detail-panel">
        <template v-if="!selectedDomain">
          <div class="no-selection">
            <div class="no-sel-icon"><el-icon :size="48"><Connection /></el-icon></div>
            <div class="no-sel-title">选择左侧域名查看资产链路</div>
            <div class="no-sel-desc">从 域名 → 入口 → 后端服务 → 虚拟机 的完整关联关系</div>
          </div>
        </template>

        <template v-else>
          <!-- 域名标题 -->
          <div class="detail-header">
            <div class="detail-domain">
              {{ selectedDomain.domain }}
              <el-tag v-if="selectedDomain.isPseudo" size="small" type="info" style="margin-left:8px;">VS 直连</el-tag>
            </div>
            <div class="detail-sources">
              <el-tag v-for="s in selectedDomain.sources" :key="s" size="small"
                :type="sourceTagType(s)">
                {{ s }}
              </el-tag>
            </div>
          </div>

          <!-- VIP 入口卡片 -->
          <div class="vip-cards">
            <div v-for="(vip, vi) in vipEntries" :key="vi" class="vip-card">
              <div class="vip-card-header" :class="'entry-'+vip.entryType">
                <span class="vip-label">{{ vip.entryLabel }}</span>
                <span class="vip-addr">{{ vip.publicIP || '直连' }}<template v-if="vip.port">:{{ vip.port }}</template></span>
                <span v-if="vip.vsName" class="vip-vs-name">{{ vip.vsName }}</span>
                <span v-if="vip.poolName" class="vip-pool-name" title="Pool">{{ vip.poolName }}</span>
                <span v-if="vip.ruleName" class="vip-rule-name" title="Rule">{{ vip.ruleName }}</span>
                <span v-if="vip.rulesText && vip.rulesText.toLowerCase().includes('redirect')" class="vip-redirect-hint" title="HTTP→HTTPS 重定向">
                  <el-icon :size="12"><Right /></el-icon>HTTPS重定向
                </span>
                <span v-else-if="vip.rulesText" class="vip-rules-hint">{{ vip.rulesText }}</span>
                <span class="vip-member-count">{{ vip.members.length }} 后端</span>
              </div>

              <div class="member-list">
                <div v-for="(m, mi) in vip.members" :key="mi" class="member-row">
                  <div class="member-main">
                    <span class="member-addr">
                      {{ m.internalIP || '—' }}<template v-if="m.internalPort">:{{ m.internalPort }}</template>
                    </span>
                    <span v-if="m.status" class="member-status" :class="'st-'+m.status">
                      {{ statusLabel(m.status) }}
                    </span>
                    <span v-if="m.vms.length" class="member-vm-count">{{ m.vms.length }} VM</span>
                  </div>

                  <!-- VM 列表 -->
                  <div v-if="m.vms.length" class="vm-list">
                    <div v-for="(vm, vmi) in m.vms" :key="vmi" class="vm-row">
                      <div class="vm-name">
                        <el-icon :size="14"><Cloudy /></el-icon>
                        {{ vm.vmName }}
                      </div>
                      <div class="vm-attrs">
                        <span v-if="vm.ipAddress" class="vm-attr">
                          <span class="attr-label">IP</span>{{ vm.ipAddress }}
                        </span>
                        <span v-if="vm.macAddress" class="vm-attr">
                          <span class="attr-label">MAC</span><code>{{ vm.macAddress }}</code>
                        </span>
                        <span v-if="vm.esxiHost" class="vm-attr">
                          <span class="attr-label">宿主机</span>{{ vm.esxiHost }}
                        </span>
                        <span v-if="vm.network" class="vm-attr">
                          <span class="attr-label">网络</span>{{ vm.network }}
                        </span>
                        <span v-if="vm.vlan" class="vm-attr">
                          <span class="attr-label">VLAN</span>{{ vm.vlan }}
                        </span>
                        <span v-if="vm.folder" class="vm-attr">
                          <span class="attr-label">文件夹</span>{{ vm.folder }}
                        </span>
                      </div>
                      <!-- 椒图数据 -->
                      <div v-if="vm.qaxMachineName" class="qax-row">
                        <div class="qax-header">
                          <el-icon :size="13"><Monitor /></el-icon>
                          椒图
                          <span class="qax-name">{{ vm.qaxMachineName }}</span>
                          <span class="qax-status" :class="qaxStatusClass(vm.qaxOnlineStatus)">{{ vm.qaxOnlineStatus }}</span>
                        </div>
                        <div class="qax-attrs">
                          <span v-if="vm.qaxOs" class="vm-attr">
                            <span class="attr-label">OS</span>{{ vm.qaxOs }}
                          </span>
                          <span v-if="vm.qaxKernel" class="vm-attr">
                            <span class="attr-label">内核</span>{{ vm.qaxKernel }}
                          </span>
                          <span v-if="vm.qaxCpu" class="vm-attr">
                            <span class="attr-label">CPU</span>{{ vm.qaxCpu }}
                          </span>
                          <span v-if="vm.qaxMemory" class="vm-attr">
                            <span class="attr-label">内存</span>{{ vm.qaxMemory }}
                          </span>
                          <span v-if="vm.qaxDisk" class="vm-attr">
                            <span class="attr-label">磁盘</span>{{ vm.qaxDisk }}
                          </span>
                          <span v-if="vm.qaxGroup" class="vm-attr">
                            <span class="attr-label">分组</span>{{ vm.qaxGroup }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div v-else class="vm-list-empty">未关联虚拟机</div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getAssetProfile, exportAssetProfile } from '@/api/asset'

const loading = ref(false)
const exporting = ref(false)
const search = ref('')
const showZDNS = ref(true)
const showF5 = ref(true)
const showVCenter = ref(true)
const showSwitch = ref(true)
const showQAX = ref(true)
const showPseudo = ref(true)

const rawRows = ref([])
const selectedDomain = ref(null)

const STATUS_MAP = { up: '在线', down: '离线', 'user-down': '禁用', 'user-up': '启用' }
function statusLabel(s) { return STATUS_MAP[s] || s }

function sourceTagType(s) {
  if (s === 'ZDNS') return 'primary'
  if (s === 'F5') return 'success'
  if (s === 'vCenter') return 'warning'
  if (s === 'Switch') return 'info'
  if (s === '椒图') return 'danger'
  return ''
}

function qaxStatusClass(s) {
  if (s === '在线') return 'qax-online'
  if (s === '离线') return 'qax-offline'
  return 'qax-other'
}

// ── IP 入口分类 ──
function classifyEntry(ip) {
  if (!ip) return { label: '直连', type: 'direct' }
  if (ip.includes(':')) return { label: 'IPv6公网入口', type: 'ipv6' }
  const parts = ip.split('.')
  if (parts.length === 4) {
    const a = parseInt(parts[0]), b = parseInt(parts[1])
    if (a === 10) return { label: '内网入口', type: 'private' }
    if (a === 172 && b >= 16 && b <= 31) return { label: '内网入口', type: 'private' }
    if (a === 192 && b === 168) return { label: '内网入口', type: 'private' }
  }
  return { label: 'IPv4公网入口', type: 'public' }
}

// ── 构建域名树 ──
const domainTree = computed(() => {
  const domainMap = new Map()

  for (const row of rawRows.value) {
    const domain = row['域名']
    const isPseudo = row['is_pseudo'] === true
    const sources = (row['来源'] || '').split(',').filter(Boolean)

    if (!domain) continue

    if (!domainMap.has(domain)) {
      domainMap.set(domain, { domain, isPseudo, sources: new Set(), vips: new Map() })
    }
    const entry = domainMap.get(domain)
    for (const s of sources) entry.sources.add(s)

    const vipIP = row['公网IP']
    const vipPort = row['端口']
    const vipKey = vipIP ? `${vipIP}::${vipPort || ''}` : '__direct__'

    if (!entry.vips.has(vipKey)) {
      entry.vips.set(vipKey, {
        publicIP: vipIP,
        port: vipPort,
        vsName: row['f5_vs_name'] || '',
        poolName: row['f5_pool_name'] || '',
        ruleName: row['f5_rule_name'] || '',
        rulesText: row['f5_rules_text'] || '',
        members: new Map(),
      })
    }
    const vip = entry.vips.get(vipKey)
    // 补充 F5 名称（首次无值，后续行补充）
    if (!vip.vsName && row['f5_vs_name']) vip.vsName = row['f5_vs_name']
    if (!vip.poolName && row['f5_pool_name']) vip.poolName = row['f5_pool_name']
    if (!vip.ruleName && row['f5_rule_name']) vip.ruleName = row['f5_rule_name']

    const memIP = row['内网服务IP']
    const memPort = row['内网端口']
    const memKey = memIP ? `${memIP}::${memPort || ''}` : `__nomem_${vipKey}`

    if (!vip.members.has(memKey)) {
      vip.members.set(memKey, {
        internalIP: memIP,
        internalPort: memPort,
        status: row['状态'],
        vms: [],
      })
    }
    const member = vip.members.get(memKey)

    if (row['虚拟机名称']) {
      const exists = member.vms.some(v => v.vmName === row['虚拟机名称'])
      if (!exists) {
        member.vms.push({
          vmName: row['虚拟机名称'],
          ipAddress: row['IP地址'],
          macAddress: row['MAC地址'],
          network: row['网络'],
          vlan: row['VLAN'],
          folder: row['文件夹'],
          esxiHost: row['esxi_host'] || '',
          qaxMachineName: row['qax_machine_name'] || '',
          qaxOs: row['qax_os'] || '',
          qaxKernel: row['qax_kernel'] || '',
          qaxCpu: row['qax_cpu'] || '',
          qaxMemory: row['qax_memory'] || '',
          qaxDisk: row['qax_disk'] || '',
          qaxGroup: row['qax_group'] || '',
          qaxOnlineStatus: row['qax_online_status'] || '',
        })
      }
    }
  }

  const domains = []
  for (const [, entry] of domainMap) {
    const vips = []
    let totalMembers = 0; let totalVMs = 0
    for (const [, vip] of entry.vips) {
      const members = []
      for (const [, m] of vip.members) {
        members.push({ ...m, vms: [...m.vms] })
        totalVMs += m.vms.length
      }
      const classif = classifyEntry(vip.publicIP)
      vips.push({
        publicIP: vip.publicIP, port: vip.port,
        vsName: vip.vsName, poolName: vip.poolName, ruleName: vip.ruleName,
        rulesText: vip.rulesText,
        entryType: classif.type, entryLabel: classif.label,
        members,
      })
      totalMembers += members.length
    }
    vips.sort((a, b) => {
      if (!a.publicIP && !b.publicIP) return 0
      if (!a.publicIP) return 1
      if (!b.publicIP) return -1
      return a.publicIP.localeCompare(b.publicIP)
    })
    domains.push({
      domain: entry.domain, isPseudo: entry.isPseudo,
      sources: [...entry.sources].sort(),
      vipCount: entry.vips.size, memberCount: totalMembers, vmCount: totalVMs,
      vips,
    })
  }

  domains.sort((a, b) => {
    if (a.isPseudo !== b.isPseudo) return a.isPseudo ? 1 : -1
    return a.domain.localeCompare(b.domain)
  })
  return domains
})

const realDomains = computed(() => domainTree.value.filter(d => !d.isPseudo))
const pseudoDomains = computed(() => domainTree.value.filter(d => d.isPseudo))

const filteredDomains = computed(() => {
  let list = realDomains.value
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(d => d.domain.toLowerCase().includes(q))
  }
  if (!showZDNS.value) list = list.filter(d => !d.sources.includes('ZDNS'))
  if (!showF5.value) list = list.filter(d => !d.sources.includes('F5'))
  if (!showVCenter.value) list = list.filter(d => !d.sources.includes('vCenter'))
  if (!showSwitch.value) list = list.filter(d => !d.sources.includes('Switch'))
  if (!showQAX.value) list = list.filter(d => !d.sources.includes('椒图'))
  return list
})

// 选中域的 VIP 入口（带分类排序）
const vipEntries = computed(() => {
  if (!selectedDomain.value) return []
  const vips = [...selectedDomain.value.vips]
  const order = { public: 0, ipv6: 1, private: 2, direct: 3 }
  return vips.sort((a, b) => (order[a.entryType] ?? 9) - (order[b.entryType] ?? 9))
})

const totalVIPs = computed(() => {
  const set = new Set()
  for (const d of realDomains.value)
    for (const v of d.vips)
      if (v.publicIP) set.add(v.publicIP + ':' + (v.port || ''))
  return set.size
})
const totalMembers = computed(() => realDomains.value.reduce((s, d) => s + d.memberCount, 0))
const totalVMs = computed(() => realDomains.value.reduce((s, d) => s + d.vmCount, 0))
const totalVLANs = computed(() => {
  const set = new Set()
  for (const d of domainTree.value)
    for (const v of d.vips)
      for (const m of v.members)
        for (const vm of m.vms)
          if (vm.vlan) set.add(vm.vlan)
  return set.size
})
const totalFolders = computed(() => {
  const set = new Set()
  for (const d of domainTree.value)
    for (const v of d.vips)
      for (const m of v.members)
        for (const vm of m.vms)
          if (vm.folder) set.add(vm.folder)
  return set.size
})

function selectDomain(d) {
  selectedDomain.value = d
}

function onSearchInput() {
  if (filteredDomains.value.length > 0 && (!selectedDomain.value || !filteredDomains.value.find(d => d.domain === selectedDomain.value.domain))) {
    selectedDomain.value = filteredDomains.value[0]
  }
}

function applyFilters() {
  if (filteredDomains.value.length > 0 && (!selectedDomain.value || !filteredDomains.value.find(d => d.domain === selectedDomain.value.domain))) {
    selectedDomain.value = filteredDomains.value[0]
  }
}

async function fetchData() {
  loading.value = true
  try {
    const data = await getAssetProfile({
      page: 1, size: 200000,
      search: '', sort_by: '', sort_dir: 'asc',
      status: '', network: '', source: '',
    })
    rawRows.value = data.rows
    if (realDomains.value.length > 0) {
      selectedDomain.value = realDomains.value[0]
    }
  } finally {
    loading.value = false
  }
}

async function exportExcel() {
  exporting.value = true
  try { await exportAssetProfile({ search: '', status: '', network: '', source: '' }) }
  finally { exporting.value = false }
}

onMounted(fetchData)
</script>

<style scoped>
.asset-profile-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 100px);
}

/* ── 顶部栏 ── */
.top-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.top-bar h2 { margin: 0; font-size: 20px; font-weight: 700; white-space: nowrap; }
.stats-ribbon {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  font-size: 13px; color: var(--color-text-secondary);
}
.stat-chip {
  padding: 2px 6px; border-radius: 4px; cursor: default; white-space: nowrap;
}
.stat-chip.active { cursor: pointer; transition: background 0.15s; }
.stat-chip.active:hover { background: var(--color-border-light); }
.stat-chip.pseudo { color: #909399; }
.stat-chip strong { color: var(--color-text); margin-left: 2px; }
.stat-sep { color: #d0d0d0; }
.export-btn { margin-left: auto; flex-shrink: 0; }

/* ── 主体 ── */
.main-area {
  display: flex; flex: 1; min-height: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md); overflow: hidden;
  background: var(--color-bg-card);
}

/* ── 左侧域名面板 ── */
.domain-panel {
  width: 330px; flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  display: flex; flex-direction: column;
  background: var(--color-bg);
}
.panel-search { padding: 12px 12px 0; }
.panel-filters {
  display: flex; gap: 4px; padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}
.panel-filters :deep(.el-checkbox-button__inner) {
  font-size: 11px; padding: 2px 8px;
}
.domain-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.list-section-label {
  padding: 6px 12px; font-size: 11px; font-weight: 600;
  color: #909399; text-transform: uppercase; letter-spacing: 0.5px;
}
.list-section-label .count { font-weight: 400; }
.domain-item {
  padding: 10px 12px; cursor: pointer; transition: background 0.12s;
  border-left: 3px solid transparent;
}
.domain-item:hover { background: rgba(99,102,241,0.04); }
.domain-item.selected { background: rgba(99,102,241,0.08); border-left-color: #6366f1; }
.domain-name { font-size: 14px; font-weight: 600; color: var(--color-text); word-break: break-all; line-height: 1.4; }
.domain-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.source-dots { display: flex; gap: 2px; }
.dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 3px;
  font-size: 10px; font-weight: 700; color: #fff;
}
.dot.zdns { background: #6366f1; }
.dot.f5   { background: #10b981; }
.dot.vc   { background: #f59e0b; }
.dot.sw   { background: #06b6d4; }
.dot.qax  { background: #ef4444; }
.domain-counts { font-size: 12px; color: #909399; }
.list-empty { padding: 20px; text-align: center; color: #c0c4cc; font-size: 13px; }

.pseudo-section { border-top: 1px solid var(--color-border); }
.pseudo-header {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 12px; font-size: 12px; color: #909399; cursor: pointer; user-select: none;
}
.pseudo-toggle {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 12px; font-size: 12px; color: #909399; cursor: pointer;
  border-top: 1px solid var(--color-border);
}
.pseudo-item { opacity: 0.8; }
.pseudo-item .domain-name {
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  font-size: 13px; color: #909399;
}

/* ── 右侧详情面板 ── */
.detail-panel { flex: 1; overflow-y: auto; padding: 20px 24px; min-width: 0; }

.no-selection {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; color: #c0c4cc;
}
.no-sel-icon { margin-bottom: 16px; opacity: 0.5; }
.no-sel-title { font-size: 16px; color: #909399; margin-bottom: 8px; }
.no-sel-desc { font-size: 13px; }

/* 域名标题 */
.detail-header {
  margin-bottom: 20px; padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
}
.detail-domain {
  font-size: 20px; font-weight: 700; color: var(--color-text);
  word-break: break-all; display: flex; align-items: center;
}
.detail-sources { display: flex; gap: 6px; margin-top: 8px; }

/* VIP 卡片 */
.vip-cards { display: flex; flex-direction: column; gap: 12px; }
.vip-card {
  border: 1px solid var(--color-border); border-radius: 8px; overflow: hidden;
}
.vip-card-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; border-bottom: 1px solid var(--color-border);
}
.vip-card-header.entry-private { background: #f0f9ff; }
.vip-card-header.entry-public  { background: #fef2f2; }
.vip-card-header.entry-ipv6    { background: #f5f3ff; }
.vip-card-header.entry-direct  { background: #f8f9fb; }

.vip-label {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 3px; white-space: nowrap;
}
.entry-private .vip-label { color: #0369a1; background: rgba(3,105,161,0.1); }
.entry-public  .vip-label { color: #dc2626; background: rgba(220,38,38,0.08); }
.entry-ipv6    .vip-label { color: #7c3aed; background: rgba(124,58,237,0.08); }
.entry-direct  .vip-label { color: #909399; background: rgba(144,147,153,0.08); }

.vip-addr {
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  font-size: 14px; font-weight: 600; color: var(--color-text);
}
.vip-vs-name {
  font-size: 12px; color: #6366f1; font-weight: 500;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.vip-pool-name {
  font-size: 11px; color: #10b981; background: rgba(16,185,129,0.08);
  padding: 1px 6px; border-radius: 3px; max-width: 160px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.vip-rule-name {
  font-size: 11px; color: #f59e0b; background: rgba(245,158,11,0.08);
  padding: 1px 6px; border-radius: 3px; max-width: 160px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.vip-redirect-hint {
  font-size: 11px; color: #2563eb; background: rgba(37,99,235,0.08);
  padding: 2px 6px; border-radius: 3px; display: inline-flex; align-items: center; gap: 2px;
}
.vip-rules-hint {
  font-size: 11px; color: #7c3aed; background: rgba(124,58,237,0.06);
  padding: 2px 6px; border-radius: 3px; max-width: 200px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.vip-member-count { margin-left: auto; font-size: 12px; color: #909399; }

/* 后端成员 */
.member-list { padding: 4px 0; }
.member-row { padding: 10px 16px 10px 24px; border-bottom: 1px solid #f0f0f0; }
.member-row:last-child { border-bottom: none; }
.member-main { display: flex; align-items: center; gap: 8px; }
.member-addr {
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
  font-size: 13px; color: var(--color-text);
}
.member-status {
  font-size: 11px; padding: 1px 6px; border-radius: 3px; font-weight: 500;
}
.st-up     { color: #16a34a; background: rgba(22,163,74,0.08); }
.st-down   { color: #dc2626; background: rgba(220,38,38,0.08); }
.st-user-down { color: #909399; background: rgba(144,147,153,0.08); }
.st-user-up   { color: #2563eb; background: rgba(37,99,235,0.08); }
.member-vm-count { margin-left: auto; font-size: 12px; color: #909399; }

/* VM 列表 */
.vm-list { margin-top: 8px; padding-left: 20px; border-left: 2px solid #e5e7eb; }
.vm-list-empty { margin-top: 6px; font-size: 12px; color: #c0c4cc; padding-left: 20px; }
.vm-row { padding: 8px 0; }
.vm-row + .vm-row { border-top: 1px dashed #f0f0f0; }
.vm-name {
  display: flex; align-items: center; gap: 6px;
  font-size: 14px; font-weight: 600; color: #f59e0b; margin-bottom: 6px;
}
.vm-attrs {
  display: flex; flex-wrap: wrap; gap: 4px 16px;
}
.vm-attr {
  font-size: 12px; color: #606266;
  display: inline-flex; align-items: center; gap: 4px;
}
.attr-label {
  font-size: 10px; color: #909399; text-transform: uppercase; letter-spacing: 0.3px;
}
.vm-attr code {
  font-size: 12px; background: #f5f5f5; padding: 1px 4px; border-radius: 2px;
  font-family: ui-monospace, 'Cascadia Code', 'Fira Code', monospace;
}

/* 椒图数据行 */
.qax-row {
  margin-top: 8px; padding: 8px 12px;
  background: rgba(239,68,68,0.04); border-radius: 6px;
  border: 1px solid rgba(239,68,68,0.1);
}
.qax-header {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: #ef4444;
}
.qax-name { color: var(--color-text); font-weight: 500; }
.qax-status { font-size: 11px; padding: 0 6px; border-radius: 3px; }
.qax-online { color: #16a34a; background: rgba(22,163,74,0.08); }
.qax-offline { color: #dc2626; background: rgba(220,38,38,0.08); }
.qax-other { color: #909399; background: rgba(144,147,153,0.08); }
.qax-attrs { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 4px; }
</style>
