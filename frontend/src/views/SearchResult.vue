<template>
  <div class="search-result">
    <div class="page-header">
      <h2>搜索结果：{{ query }}</h2>
    </div>

    <!-- ═══════════ 第一级：资产画像结果 ═══════════ -->
    <template v-if="assetResults.length > 0">
      <div class="result-section">
        <span class="section-badge">资产画像</span>
        <span class="section-count">共 {{ assetTotal }} 条</span>
      </div>
      <el-table :data="pagedAssetResults" stripe v-loading="loading" size="small">
        <el-table-column prop="域名" label="域名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="来源" label="来源" width="100" />
        <el-table-column prop="公网IP" label="公网IP" width="140" />
        <el-table-column prop="端口" label="端口" width="70" />
        <el-table-column prop="内网服务IP" label="内网IP" width="140" />
        <el-table-column prop="内网端口" label="内网端口" width="80" />
        <el-table-column prop="状态" label="状态" width="70">
          <template #default="{ row }">{{ row['状态'] || '-' }}</template>
        </el-table-column>
        <el-table-column prop="虚拟机名称" label="虚拟机" min-width="150" show-overflow-tooltip />
        <el-table-column prop="IP地址" label="IP地址" width="140" />
        <el-table-column prop="MAC地址" label="MAC地址" width="150" show-overflow-tooltip />
        <el-table-column prop="网络" label="网络" width="120" show-overflow-tooltip />
      </el-table>
      <div class="pagination-wrap" v-if="assetTotal > assetSize">
        <el-pagination v-model:current-page="assetPage" :page-size="assetSize" :total="assetTotal"
          layout="prev, pager, next" small @current-change="onAssetPageChange" />
      </div>
    </template>

    <!-- ═══════════ 第二级：扫描结果（仅资产画像无结果时显示） ═══════════ -->
    <template v-else>
      <div class="result-section" v-if="scanResults.length > 0">
        <span class="section-badge">交换机扫描结果</span>
        <span class="section-count">共 {{ scanResults.length }} 条</span>
      </div>
      <el-table v-if="scanResults.length > 0" :data="scanResults" stripe v-loading="loading" size="small">
        <el-table-column prop="switch_name" label="交换机" width="160" show-overflow-tooltip />
        <el-table-column prop="switch_ip" label="交换机IP" width="140" />
        <el-table-column prop="ip_address" label="IP 地址" width="140" />
        <el-table-column prop="mac_address" label="MAC 地址" width="150" />
        <el-table-column prop="vlan_bd" label="VLAN/BD" width="90">
          <template #default="{ row }">{{ row.vlan_bd ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="vlan_type" label="VLAN类型" width="100">
          <template #default="{ row }">{{ row.vlan_type ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="physical_port" label="物理端口" min-width="160" show-overflow-tooltip />
        <el-table-column prop="virtual_port" label="虚拟端口" min-width="160" show-overflow-tooltip />
        <el-table-column prop="switch_type" label="类型" width="70">
          <template #default="{ row }">{{ row.switch_type === 'L3' ? '三层' : '二层' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && scanResults.length === 0" description="未找到匹配记录" :image-size="80" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'
import { formatTime } from '@/utils/format'

const route = useRoute()
const query = ref(route.query.q || '')
const loading = ref(false)

// 资产画像
const assetResults = ref([])
const assetAll = ref([])
const assetPage = ref(1)
const assetSize = ref(30)
const assetTotal = ref(0)

const pagedAssetResults = computed(() => {
  const start = (assetPage.value - 1) * assetSize.value
  return assetAll.value.slice(start, start + assetSize.value)
})

function onAssetPageChange() {
  // pagedAssetResults 已自动更新
}

// 扫描结果
const scanResults = ref([])


async function doSearch(q) {
  if (!q || q.length < 2) return
  loading.value = true
  try {
    // 第一级：资产画像
    const { data: assetData } = await api.get('/asset-profile', {
      params: { search: q, size: 200 }
    })
    if (assetData.rows && assetData.rows.length > 0) {
      assetAll.value = assetData.rows
      assetResults.value = assetData.rows.slice(0, assetSize.value)
      assetTotal.value = assetData.rows.length
      assetPage.value = 1
      scanResults.value = []
      return
    }

    // 第二级：扫描结果
    const { data: scanData } = await api.get('/search', { params: { q, limit: 100 } })
    scanResults.value = scanData
    assetResults.value = []
    assetAll.value = []
  } catch { /* handled */ }
  finally { loading.value = false }
}

onMounted(() => {
  if (query.value) doSearch(query.value)
})

watch(() => route.query.q, (val) => {
  if (val) {
    query.value = val
    doSearch(val)
  }
})
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}
.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.result-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.section-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(99,102,241,0.1);
  color: #6366f1;
}
.section-count {
  font-size: 12px;
  color: #909399;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
