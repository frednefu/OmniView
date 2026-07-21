<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2>系统监控 — {{ sysName }}</h2>
        <p class="page-desc">组件拓扑结构 · 运行状态实时展示</p>
      </div>
      <div class="header-actions">
        <el-select v-model="systemId" placeholder="选择信息系统" style="width:300px" filterable @change="loadSystem">
          <el-option v-for="s in sysList" :key="s.id" :label="s.system_name" :value="s.id" />
        </el-select>
      </div>
    </div>

    <el-row :gutter="16">
      <!-- 拓扑图 -->
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <strong>拓扑结构</strong>
              <el-button size="small" :loading="savingPos" @click="savePositions">保存位置</el-button>
            </div>
          </template>
          <div v-if="topoNodes.length > 0" ref="graphRef" class="graph-container"></div>
          <el-empty v-else description="暂无关联资产，请先关联" :image-size="80">
            <el-button type="primary" size="small" @click="goLink">去关联资产</el-button>
          </el-empty>
        </el-card>
      </el-col>

      <!-- 状态面板 -->
      <el-col :span="8">
        <el-card shadow="hover" class="status-panel">
          <template #header><strong>组件状态</strong></template>
          <div class="status-summary">
            <div class="status-item clickable" :class="{active: statusFilter==='up'}" @click="toggleFilter('up')"><span class="dot up"></span>正常: {{ stats.up }}</div>
            <div class="status-item clickable" :class="{active: statusFilter==='down'}" @click="toggleFilter('down')"><span class="dot down"></span>异常: {{ stats.down }}</div>
            <div class="status-item clickable" :class="{active: statusFilter==='unknown'}" @click="toggleFilter('unknown')"><span class="dot unknown"></span>未知: {{ stats.unknown }}</div>
          </div>
          <el-table :data="filteredAssets" stripe size="small" style="margin-top:12px;flex:1">
            <el-table-column label="类型" width="75">
              <template #default="{row}">{{ typeLabel(row.asset_type) }}</template>
            </el-table-column>
            <el-table-column prop="asset_key" label="资产" min-width="120" show-overflow-tooltip />
            <el-table-column prop="asset_ip" label="IP" width="140" show-overflow-tooltip />
            <el-table-column label="角色" width="80">
              <template #default="{row}">
                <el-tag size="small">{{ row.asset_label || '-' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{row}">
                <el-tag :type="row.status==='up'?'success':row.status==='warning'||row.status==='remind'?'warning':row.status==='down'?'danger':'info'" size="small">{{ row.status_label || '未知' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api from '@/api/index'

const route = useRoute()
const router = useRouter()
const systemId = ref(Number(route.params.id) || null)
const sysName = ref('')
const sysList = ref([])
const assets = ref([])
const topoNodes = ref([])
const graphRef = ref(null)
let graphChart = null

const statusFilter = ref('')
const filteredAssets = computed(() => {
  if (!statusFilter.value) return assets.value
  return assets.value.filter(a => { const s = (a.status === 'up' || a.status === 'warning' || a.status === 'remind') ? 'up' : a.status === 'down' ? 'down' : 'unknown'; return s === statusFilter.value })
})
const stats = computed(() => {
  let up = 0, down = 0, unknown = 0
  for (const a of assets.value) {
    if (a.status === 'up' || a.status === 'warning' || a.status === 'remind') up++
    else if (a.status === 'down') down++
    else unknown++
  }
  return { up, down, unknown }
})
function toggleFilter(val) {
  statusFilter.value = statusFilter.value === val ? '' : val
}

const catColors = {
  system: '#6366f1', domain: '#10b981', vm: '#f59e0b', f5_vs: '#06b6d4',
  f5_member: '#14b8a6', backup: '#8b5cf6', qax: '#ec4899',
}
const catNames = { domain:'域名', vm:'虚拟机', f5_vs:'F5 VS', f5_member:'F5成员', backup:'备份', qax:'椒图' }
function typeLabel(t) { return catNames[t] || t }

async function fetchSysList() {
  const { data } = await api.get('/monitor/systems', { params: { search: '' } })
  sysList.value = (data.items || []).filter(s => s.asset_count > 0)
}

async function loadSystem() {
  if (!systemId.value) return
  const sys = sysList.value.find(s => s.id === systemId.value)
  if (sys) sysName.value = sys.system_name

  // 加载资产
  try {
    const { data } = await api.get(`/monitor/systems/${systemId.value}/assets`)
    assets.value = data.items || []
  } catch {}

  // 加载拓扑
  try {
    const topoRes = await api.get(`/monitor/systems/${systemId.value}/topology`)
    const topoData = topoRes.data
    topoNodes.value = topoData.nodes || []
    // 加载已保存位置（在 renderGraph 外部加载）
    let savedPos = {}
    try {
      const posRes = await api.get(`/monitor/systems/${systemId.value}/topo-positions`)
      if (posRes.data && posRes.data.positions) savedPos = posRes.data.positions
    } catch (e) { console.error('load positions error', e) }
    await nextTick()
    renderGraph(topoData, savedPos)
  } catch (e) { console.error('topology error', e) }
}

// 节点位置（渲染时生成，拖动时更新）
let currentPositions = {}
const savingPos = ref(false)
async function savePositions() {
  if (!systemId.value) return
  // 过滤无效位置
  const clean = {}
  for (const [name, pos] of Object.entries(currentPositions)) {
    if (pos && typeof pos.x === 'number' && typeof pos.y === 'number' && isFinite(pos.x) && isFinite(pos.y)) {
      clean[name] = { x: Math.round(pos.x), y: Math.round(pos.y) }
    }
  }
  const keys = Object.keys(clean)
  if (keys.length === 0) { ElMessage.warning('无有效位置数据可保存'); return }
  currentPositions = clean

  savingPos.value = true
  try {
    await api.put(`/monitor/systems/${systemId.value}/topo-positions`, { positions: currentPositions })
    ElMessage.success(`已保存 ${Object.keys(currentPositions).length} 个节点位置`)
  } catch { ElMessage.error('保存失败') }
  finally { savingPos.value = false }
}

function renderGraph(data, savedPos = {}) {
  const el = graphRef.value
  if (!el || !(data.nodes && data.nodes.length > 0)) return
  if (graphChart) graphChart.dispose()
  graphChart = echarts.init(el)

  const catColorMap = {
    system: '#6366f1', domain: '#f59e0b', f5_vs: '#06b6d4',
    f5_member: '#14b8a6', vm: '#f97316', backup: '#8b5cf6', qax: '#ec4899',
  }
  const catCN = {
    system: '信息系统', domain: '域名', f5_vs: 'F5 VS',
    f5_member: 'F5成员', vm: '虚拟机', backup: '备份', qax: '椒图',
  }

  // 分层Y坐标
  const layerY = { system: 0, domain: 130, f5_vs: 280, f5_member: 420, vm: 560, backup: 700, qax: 840 }
  const layerNodes = {}
  for (const n of (data.nodes || [])) {
    const l = layerY[n.category] !== undefined ? n.category : 'other'
    if (!layerNodes[l]) layerNodes[l] = []
    layerNodes[l].push(n)
  }
  for (const k of Object.keys(layerNodes)) {
    layerNodes[k].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name))
  }

  // 系统状态：异常优先
  // 系统状态：使用资产表数据（比拓扑节点更全面）
  let sysStatus = 'up'
  for (const a of assets.value) {
    if (a.status === 'down' || a.status === 'remind') { sysStatus = 'down'; break }
    if (a.status === 'unknown') sysStatus = 'unknown'
  }

  const gapX = 150
  const nodes = []
  currentPositions = {}  // 重置
  for (const cat of Object.keys(layerY)) {
    const items = layerNodes[cat] || []
    const y = layerY[cat] || 0
    const totalW = (items.length - 1) * gapX
    items.forEach((n, i) => {
      const saved = savedPos[n.name]
      const hasSaved = saved && typeof saved.x === 'number' && typeof saved.y === 'number'
      const nx = hasSaved ? saved.x : (i * gapX - totalW / 2)
      const ny = hasSaved ? saved.y : y
      // 保存到内存变量
      currentPositions[n.name] = { x: Math.round(nx), y: Math.round(ny) }
      nodes.push({
        name: n.name, category: n.category,
        symbolSize: n.category === 'system' ? 48 : 28,
        x: nx, y: ny,
        itemStyle: {
          color: catColorMap[n.category] || '#94a3b8',
          borderColor: n.category === 'system'
            ? (sysStatus === 'up' ? '#10b981' : sysStatus === 'down' ? '#ef4444' : '#94a3b8')
            : (n.status === 'up' ? '#10b981' : n.status === 'down' ? '#ef4444' : '#94a3b8'),
          borderWidth: 4,
        },
        label: { show: true, fontSize: 10, formatter: n.label || n.name },
      })
    })
  }

  const links = (data.links || []).map(l => ({
    source: l.source, target: l.target,
    label: { show: true, fontSize: 9, formatter: l.label },
    lineStyle: { color: '#cbd5e1', width: 1, curveness: 0.15 },
  }))

  const legendData = Object.entries(catCN).map(([k]) => k)

  graphChart.setOption({
    tooltip: {
      formatter: p => {
        if (p.dataType === 'node') {
          const cn = catCN[p.data.category] || p.data.category
          const sc = p.data.itemStyle?.borderColor
          const st = sc === '#10b981' ? '正常' : sc === '#ef4444' ? '异常' : '未知'
          return `${p.name}<br/>类型: ${cn}<br/>状态: ${st}`
        }
        return ''
      }
    },
    legend: {
      data: legendData,
      bottom: 0,
      textStyle: { fontSize: 13 },
      formatter: name => catCN[name] || name,
      itemWidth: 16, itemHeight: 16,
    },
    series: [{
      type: 'graph', layout: 'none',
      roam: true, draggable: true,
      categories: Object.entries(catColorMap).map(([k, v]) => ({
        name: k, itemStyle: { color: v }
      })),
      nodes, links,
    }],
  })
  // 拖动节点后更新位置缓存
  function capturePositions() {
    try {
      const graph = graphChart.getModel().getSeries()[0]?.getGraph()
      if (!graph) return
      const nodes = graph.getNodes()
      if (!nodes) return
      for (const node of nodes) {
        const name = node.getName()
        const layout = node.getLayout()
        if (name && layout && typeof layout.x === 'number' && typeof layout.y === 'number' && isFinite(layout.x) && isFinite(layout.y)) {
          currentPositions[name] = { x: Math.round(layout.x), y: Math.round(layout.y) }
        }
      }
    } catch {}
  }
  graphChart.off('mouseup')
  graphChart.on('mouseup', capturePositions)
  graphChart.off('graphroam')
  graphChart.on('graphroam', capturePositions)
}

function goLink() { router.push('/monitor/link') }

onMounted(async () => {
  await fetchSysList()
  if (systemId.value) loadSystem()
})

onBeforeUnmount(() => { graphChart?.dispose() })
</script>

<style scoped>
.page { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 20px; }
.page-desc { margin: 4px 0 0; font-size: 13px; color: var(--color-text-muted); }
.header-actions { display: flex; gap: 10px; }

.graph-container { height: 520px; }

.status-panel { height: 100%; }
.status-panel :deep(.el-card__body) { display: flex; flex-direction: column; height: calc(100% - 56px); overflow: hidden; }
.status-summary { display: flex; gap: 16px; margin-bottom: 8px; font-size: 13px; color: var(--color-text-secondary); }
.status-item { display: flex; align-items: center; gap: 6px; }
.status-item.clickable { cursor: pointer; padding: 4px 8px; border-radius: 4px; transition: background .15s; }
.status-item.clickable:hover { background: var(--color-bg); }
.status-item.clickable.active { background: var(--color-primary-light-9, #ecf5ff); font-weight: 600; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.up { background: #10b981; }
.dot.down { background: #ef4444; }
.dot.unknown { background: #94a3b8; }
</style>

