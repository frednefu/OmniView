<template>
  <div class="page">
    <div class="page-header">
      <h2>系统监控总览</h2>
      <p class="page-desc">各信息系统组件运行状态一览</p>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background:linear-gradient(135deg,#6366f1,#818cf8)"><el-icon :size="22"><Monitor /></el-icon></div>
          <div class="stat-info"><div class="stat-value">{{ overview.total_systems }}</div><div class="stat-title">信息系统总数</div></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background:linear-gradient(135deg,#10b981,#34d399)"><el-icon :size="22"><CircleCheck /></el-icon></div>
          <div class="stat-info"><div class="stat-value">{{ overview.normal_count }}</div><div class="stat-title">正常运行</div></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background:linear-gradient(135deg,#f59e0b,#fbbf24)"><el-icon :size="22"><Warning /></el-icon></div>
          <div class="stat-info"><div class="stat-value">{{ overview.warning_count }}</div><div class="stat-title">部分异常</div></div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background:linear-gradient(135deg,#ef4444,#f87171)"><el-icon :size="22"><CircleClose /></el-icon></div>
          <div class="stat-info"><div class="stat-value">{{ overview.critical_count }}</div><div class="stat-title">严重异常</div></div>
        </div>
      </el-col>
    </el-row>

    <!-- 搜索 -->
    <div class="filter-bar">
      <el-input v-model="search" placeholder="搜索信息系统名称..." clearable style="width:300px" @keyup.enter="fetchOverview" @clear="fetchOverview" />
    </div>

    <!-- 系统卡片网格 -->
    <div v-loading="loading" class="system-grid">
      <div v-for="sys in filteredSystems" :key="sys.id" class="system-card" @click="goDetail(sys.id)">
        <div class="card-header">
          <span class="card-status" :class="'status-'+sys.status"></span>
          <span class="card-name">{{ sys.system_name }}</span>
        </div>
        <div class="card-body">
          <div class="card-stat"><span>{{ sys.asset_count }}</span> 个资产</div>
          <div class="card-stat" v-if="sys.abnormal_count > 0" style="color:#ef4444"><span>{{ sys.abnormal_count }}</span> 异常</div>
          <div class="card-stat" v-else style="color:#10b981">全部正常</div>
        </div>
      </div>
      <el-empty v-if="!loading && filteredSystems.length === 0" description="暂无关联资产的系统" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/index'

const router = useRouter()
const loading = ref(false)
const search = ref('')
const overview = ref({ total_systems: 0, normal_count: 0, warning_count: 0, critical_count: 0, systems: [] })

const filteredSystems = computed(() => {
  if (!search.value) return overview.value.systems
  const q = search.value.toLowerCase()
  return overview.value.systems.filter(s => s.system_name.toLowerCase().includes(q))
})

async function fetchOverview() {
  loading.value = true
  try {
    const { data } = await api.get('/monitor/overview')
    overview.value = data
  } catch {} finally { loading.value = false }
}

function goDetail(id) { router.push(`/monitor/${id}`) }

onMounted(fetchOverview)
</script>

<style scoped>
.page { padding: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.page-desc { margin: 4px 0 0; font-size: 13px; color: var(--color-text-muted); }

.stat-row { margin-bottom: 16px; }
.stat-card { cursor: default; display: flex; align-items: center; gap: 14px; background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 8px; padding: 16px 18px; }
.stat-icon { width: 46px; height: 46px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; }
.stat-value { font-size: 26px; font-weight: 700; }
.stat-title { font-size: 12px; color: var(--color-text-muted); }

.filter-bar { margin-bottom: 16px; }

.system-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.system-card { cursor: pointer; background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: 8px; padding: 16px; transition: box-shadow .2s; }
.system-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); }
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.card-status { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.status-normal { background: #10b981; }
.status-warning { background: #f59e0b; }
.status-critical { background: #ef4444; }
.card-name { font-size: 15px; font-weight: 600; color: var(--color-text); }
.card-body { display: flex; gap: 20px; font-size: 13px; color: var(--color-text-secondary); }
.card-stat span { font-weight: 600; color: var(--color-text); }
</style>
