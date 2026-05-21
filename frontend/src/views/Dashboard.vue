<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h2>仪表盘</h2>
        <p class="page-desc">IP 地址资源概览</p>
      </div>
      <el-button text @click="refreshAll" :loading="refreshing">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: linear-gradient(135deg, #6366f1, #818cf8);">
              <el-icon :size="22"><Monitor /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.switch_count }}</div>
              <div class="stat-title">活跃交换机</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: linear-gradient(135deg, #10b981, #34d399);">
              <el-icon :size="22"><Connection /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.total_ips }}</div>
              <div class="stat-title">唯一 IP 地址</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: linear-gradient(135deg, #f59e0b, #fbbf24);">
              <el-icon :size="22"><Discount /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.total_macs }}</div>
              <div class="stat-title">MAC 地址</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: linear-gradient(135deg, #ef4444, #f87171);">
              <el-icon :size="22"><Grid /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.subnet_count }}</div>
              <div class="stat-title">管理子网</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="14">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <strong>地址段利用率</strong>
              <span class="card-hint" v-if="subnets.length">{{ subnets.length }} 个地址段</span>
            </div>
          </template>
          <div v-if="subnets.length === 0" class="empty-chart">
            <el-empty description="暂无地址段数据" :image-size="60">
              <el-button type="primary" size="small" @click="$router.push('/subnets')">管理地址段</el-button>
            </el-empty>
          </div>
          <div v-else ref="chartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="hover" class="available-card">
          <template #header>
            <div class="card-header">
              <strong>可用 IP 查询</strong>
            </div>
          </template>
          <el-form label-width="0" class="ip-form">
            <el-select v-model="selectedSubnetId" placeholder="选择地址段查看可用 IP..." @change="fetchAvailableIps" filterable>
              <el-option v-for="s in subnets" :key="s.subnet_id"
                :label="`${s.name} (${s.subnet_cidr})`" :value="s.subnet_id" />
            </el-select>
          </el-form>
          <el-table :data="availableIps" max-height="300" v-loading="loadingIps" stripe size="small" class="ip-table">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="ip" label="IP 地址" />
            <template #empty>
              <span v-if="selectedSubnetId && !loadingIps" style="color: var(--color-text-muted);">该地址段暂无可用 IP</span>
            </template>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import api from '@/api'

const stats = reactive({
  switch_count: 0,
  total_ips: 0,
  total_macs: 0,
  subnet_count: 0,
})

const subnets = ref([])
const selectedSubnetId = ref(null)
const availableIps = ref([])
const loadingIps = ref(false)
const refreshing = ref(false)
const chartRef = ref(null)
let chartInstance = null

async function fetchStats() {
  try {
    const { data } = await api.get('/dashboard/stats')
    Object.assign(stats, data)
  } catch { /* handled by interceptor */ }
}

async function fetchUtilization() {
  try {
    const { data } = await api.get('/dashboard/subnet-utilization')
    subnets.value = data
    await nextTick()
    renderChart(data)
  } catch { /* handled by interceptor */ }
}

async function fetchAvailableIps() {
  if (!selectedSubnetId.value) return
  loadingIps.value = true
  try {
    const { data } = await api.get('/dashboard/available-ips', {
      params: { subnet_id: selectedSubnetId.value, limit: 100 }
    })
    availableIps.value = data.available_ips.map(ip => ({ ip }))
  } catch { /* handled by interceptor */ }
  finally { loadingIps.value = false }
}

async function refreshAll() {
  refreshing.value = true
  await Promise.all([fetchStats(), fetchUtilization()])
  refreshing.value = false
}

function renderChart(data) {
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const names = data.map(d => d.name + '\n' + d.subnet_cidr)
  const used = data.map(d => d.used_ips)
  const free = data.map(d => d.free_ips)

  chartInstance.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#e2e8f0',
      textStyle: { color: '#1e293b', fontSize: 13 },
      extraCssText: 'border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.08);',
      formatter: function (params) {
        const el = data[params[0].dataIndex]
        return `<b>${el.name}</b> (${el.subnet_cidr})<br/>
          已用: <b style="color:#ef4444">${el.used_ips}</b> | 可用: <b style="color:#10b981">${el.free_ips}</b> | 总计: ${el.total_ips}<br/>
          利用率: ${el.utilization_pct}%`
      }
    },
    legend: {
      data: ['已用', '可用'],
      itemWidth: 12,
      itemHeight: 12,
      itemGap: 20,
      textStyle: { color: '#64748b', fontSize: 13 },
      bottom: 0,
    },
    grid: { left: '3%', right: '4%', top: '3%', bottom: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { interval: 0, rotate: 30, fontSize: 11, color: '#64748b' },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'value',
      name: 'IP 数量',
      nameTextStyle: { color: '#94a3b8', fontSize: 12 },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
    },
    series: [
      {
        name: '已用',
        type: 'bar',
        stack: 'total',
        data: used,
        itemStyle: {
          borderRadius: [0, 0, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#f87171' },
            { offset: 1, color: '#ef4444' },
          ]),
        },
        barWidth: 28,
      },
      {
        name: '可用',
        type: 'bar',
        stack: 'total',
        data: free,
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#34d399' },
            { offset: 1, color: '#10b981' },
          ]),
        },
        barWidth: 28,
      },
    ],
  })
}

onMounted(() => {
  fetchStats()
  fetchUtilization()
})
</script>

<style scoped>
.dashboard h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.stat-row {
  margin-bottom: 20px;
}

.stat-card {
  cursor: pointer;
  transition: transform var(--transition-normal), box-shadow var(--transition-normal);
}

.stat-card:hover {
  transform: translateY(-3px);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 4px 0;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.stat-info {
  text-align: left;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.2;
}

.stat-title {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

/* 卡片头部 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-hint {
  font-size: 12px;
  color: var(--color-text-muted);
  font-weight: 400;
}

/* 图表 */
.chart-card {
  height: 100%;
}

.chart-container {
  height: 350px;
}

.empty-chart {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

/* 可用 IP */
.available-card {
  height: 100%;
}

.ip-form {
  margin-bottom: 12px;
}

.ip-table {
  border-radius: var(--radius-sm);
}
</style>
