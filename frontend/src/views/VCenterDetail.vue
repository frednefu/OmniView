<template>
  <div class="vcenter-detail">
    <div class="page-header">
      <div class="header-left">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <h2>{{ vcenter?.name || 'vCenter 详情' }}</h2>
      </div>
      <el-button v-if="authStore.isAdmin" type="primary" @click="handleScan" :loading="scanning">
        <el-icon><Refresh /></el-icon>立即扫描
      </el-button>
    </div>

    <el-descriptions v-if="vcenter" :column="3" border size="small" class="info-card">
      <el-descriptions-item label="主机地址">{{ vcenter.host }}</el-descriptions-item>
      <el-descriptions-item label="用户名">{{ vcenter.username }}</el-descriptions-item>
      <el-descriptions-item label="端口">{{ vcenter.port }}</el-descriptions-item>
      <el-descriptions-item label="扫描间隔">{{ vcenter.scan_interval > 0 ? vcenter.scan_interval + 's' : '手动' }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="vcenter.is_active ? 'success' : 'info'" size="small">
          {{ vcenter.is_active ? '启用' : '禁用' }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="扫描状态">
        <el-tag v-if="vcenter.last_scan_status === 'success'" type="success" size="small">成功</el-tag>
        <el-tag v-else-if="vcenter.last_scan_status === 'failed'" type="danger" size="small">失败</el-tag>
        <el-tag v-else-if="vcenter.last_scan_status === 'running'" type="warning" size="small">扫描中</el-tag>
        <span v-else style="color:#c0c4cc;">未扫描</span>
      </el-descriptions-item>
    </el-descriptions>

    <div v-if="vcenter?.last_scan_error" style="margin-top:12px;">
      <el-alert :title="'扫描错误: ' + vcenter.last_scan_error" type="error" show-icon :closable="false" />
    </div>

    <el-card style="margin-top:20px;">
      <template #header>
        <span>虚拟机清单（共 {{ total }} 台）</span>
      </template>
      <div class="filter-bar">
        <el-input v-model="search" placeholder="搜索 VM 名称或 IP..." clearable style="width:280px"
          @keyup.enter="fetchVMs" @clear="fetchVMs" />
        <el-button type="primary" @click="fetchVMs">查询</el-button>
      </div>

      <el-table :data="vms" stripe v-loading="loading" style="width:100%" max-height="600">
        <template #empty>
          <el-empty description="暂无虚拟机数据，请先触发扫描" :image-size="60" />
        </template>
        <el-table-column prop="vm_name" label="虚拟机名称" min-width="180" fixed show-overflow-tooltip />
        <el-table-column prop="power_state" label="电源" width="90">
          <template #default="{ row }">
            <el-tag :type="row.power_state === 'poweredOn' ? 'success' : 'info'" size="small">
              {{ row.power_state === 'poweredOn' ? '开机' : row.power_state === 'poweredOff' ? '关机' : row.power_state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP 地址" min-width="140" show-overflow-tooltip />
        <el-table-column prop="mac_address" label="MAC 地址" min-width="140" show-overflow-tooltip />
        <el-table-column prop="os_name" label="操作系统" min-width="160" show-overflow-tooltip />
        <el-table-column prop="cpu_count" label="CPU" width="60" />
        <el-table-column prop="memory_gb" label="内存(GB)" width="90" />
        <el-table-column prop="datacenter" label="数据中心" min-width="120" show-overflow-tooltip />
        <el-table-column prop="cluster" label="集群" min-width="120" show-overflow-tooltip />
        <el-table-column prop="esxi_host" label="ESXi 主机" min-width="150" show-overflow-tooltip />
        <el-table-column prop="network_name" label="网络" min-width="120" show-overflow-tooltip />
        <el-table-column prop="vlan_id" label="VLAN" width="80" />
        <el-table-column prop="resource_pool" label="资源池" min-width="120" show-overflow-tooltip />
        <el-table-column prop="vm_folder" label="文件夹" min-width="120" show-overflow-tooltip />
        <el-table-column prop="remark" label="备注" width="100" show-overflow-tooltip />
      </el-table>

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="page" :page-size="size" :total="total"
          layout="total, prev, pager, next" @current-change="fetchVMs" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getVCenter, triggerVCenterScan, getVCenterVMs } from '@/api/vcenters'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const vcenter = ref(null)
const vms = ref([])
const loading = ref(false)
const scanning = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const search = ref('')

async function fetchVCenter() {
  vcenter.value = await getVCenter(route.params.id)
}

async function fetchVMs() {
  loading.value = true
  try {
    const res = await getVCenterVMs(route.params.id, { page: page.value, size: size.value, search: search.value })
    vms.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

async function handleScan() {
  try {
    await ElMessageBox.confirm('确认扫描此 vCenter？', '确认扫描')
    scanning.value = true
    await triggerVCenterScan(route.params.id)
    ElMessage.success('扫描已触发，请稍后刷新查看结果')
    setTimeout(() => { fetchVCenter(); fetchVMs() }, 3000)
  } catch { /* cancelled */ }
  finally { scanning.value = false }
}

onMounted(() => { fetchVCenter(); fetchVMs() })
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}
.header-left h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
