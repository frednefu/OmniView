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
          <template #header><strong>拓扑结构</strong></template>
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
            <div class="status-item"><span class="dot up"></span>正常: {{ stats.up }}</div>
            <div class="status-item"><span class="dot down"></span>异常: {{ stats.down }}</div>
            <div class="status-item"><span class="dot unknown"></span>未知: {{ stats.unknown }}</div>
          </div>
          <el-table :data="assets" stripe size="small" max-height="400" style="margin-top:12px">
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
                <el-tag :type="row.status==='up'?'success':row.status==='down'?'danger':'info'" size="small">{{ row.status_label || '未知' }}</el-tag>
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

const stats = computed(() => {
  let up = 0, down = 0, unknown = 0
  for (const a of assets.value) {
    if (a.status === 'up') up++
    else if (a.status === 'down') down++
    else unknown++
  }
  return { up, down, unknown }
})

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
    const { data } = await api.get(`/monitor/systems/${systemId.value}/topology`)
    topoNodes.value = data.nodes || []
    await nextTick()
    renderGraph(data)
  } catch {}
}

function renderGraph(data) {
  const el = graphRef.value
  if (!el || !(data.nodes && data.nodes.length > 0)) return
  if (graphChart) graphChart.dispose()
  graphChart = echarts.init(el)

  const catColorMap = {
    system: '#6366f1', domain: '#f59e0b', ip: '#0ea5e9', f5_vs: '#06b6d4',
    f5_member: '#14b8a6', vm: '#f97316', backup: '#8b5cf6', qax: '#ec4899',
  }
  const catCN = {
    system: '信息系统', domain: '域名', ip: 'IP地址', f5_vs: 'F5 VS',
    f5_member: 'F5成员', vm: '虚拟机', backup: '备份', qax: '椒图',
  }

  // 层次Y坐标
  const layerY = { system: 0, domain: 120, ip: 240, f5_vs: 360, f5_member: 480, vm: 600, backup: 720, qax: 840 }
  const layerNodes = {}
  for (const n of (data.nodes || [])) {
    const l = layerY[n.category] !== undefined ? n.category : 'other'
    if (!layerNodes[l]) layerNodes[l] = []
    layerNodes[l].push(n)
  }
  for (const k of Object.keys(layerNodes)) {
    layerNodes[k].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name))
  }

  // 系统状态=子节点交集
  const childStatuses = (data.nodes || []).filter(n => n.category !== 'system').map(n => n.status)
  let sysStatus = 'up'
  if (childStatuses.includes('down')) sysStatus = 'down'
  else if (childStatuses.includes('unknown')) sysStatus = 'unknown'

  // 记忆位置
  const storageKey = `topo_pos_${systemId.value}`
  let savedPos = {}
  try { savedPos = JSON.parse(localStorage.getItem(storageKey) || '{}') } catch {}

  const gapX = 150
  const nodes = []
  for (const cat of Object.keys(layerY)) {
    const items = layerNodes[cat] || []
    const y = layerY[cat] || 0
    const totalW = (items.length - 1) * gapX
    items.forEach((n, i) => {
      const saved = savedPos[n.name]
      const hasSaved = saved && saved.x != null && saved.y != null
      nodes.push({
        name: n.name, category: n.category,
        symbolSize: n.category === 'system' ? 48 : 30,
        x: hasSaved ? saved.x : (i * gapX - totalW / 2),
        y: hasSaved ? saved.y : y,
        fixed: true,  // 全部固定，拖动后通过 mouseup 更新记忆位置
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

  // 图例使用英文key匹配节点category，显示中文标签
  const legendData = Object.entries(catCN).map(([k, v]) => k)

  graphChart.off('mouseup')
  graphChart.on('mouseup', () => {
    try {
      const opt = graphChart.getOption()
      const ns = opt.series[0]?.data || []
      const pos = {}
      ns.forEach(n => { if (n.name && n.x != null && n.y != null) pos[n.name] = { x: n.x, y: n.y } })
      localStorage.setItem(storageKey, JSON.stringify(pos))
    } catch {}
  })

  graphChart.setOption({
    tooltip: {
      formatter: p => {
        if (p.dataType === 'node') {
          const cn = catCN[p.data.category] || p.data.category
          return `${p.name}<br/>类型: ${cn}`
        }
        return ''
      }
    },
    legend: {
      data: legendData,
      bottom: 0,
      textStyle: { fontSize: 10 },
      formatter: name => catCN[name] || name,
      itemWidth: 12, itemHeight: 12,
    },
    series: [{
      type: 'graph', layout: 'force',
      force: { repulsion: 200, edgeLength: [80, 200], gravity: 0.05 },
      roam: true, draggable: true,
      categories: Object.entries(catColorMap).map(([k, v]) => ({
        name: k, itemStyle: { color: v }
      })),
      nodes, links,
    }],
  })
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
.status-summary { display: flex; gap: 16px; margin-bottom: 8px; font-size: 13px; color: var(--color-text-secondary); }
.status-item { display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot.up { background: #10b981; }
.dot.down { background: #ef4444; }
.dot.unknown { background: #94a3b8; }
</style>
