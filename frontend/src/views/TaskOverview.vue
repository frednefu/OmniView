<template>
  <div class="task-overview">
    <div class="page-header">
      <h2>待办任务</h2>
      <el-button text @click="refresh"><el-icon><Refresh /></el-icon> 刷新</el-button>
    </div>

    <div v-loading="loading">
      <!-- ═══════════ 管理员：各部门明细 ═══════════ -->
      <template v-if="authStore.isAdmin && data">
        <h3 class="section-title">各部门明细</h3>
        <el-table :data="data.dept_details" stripe max-height="500" size="small">
          <el-table-column prop="dept_name" label="部门" min-width="160" show-overflow-tooltip />
          <el-table-column label="虚拟机" width="140" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goDept(row.dept_name, 'vm')">{{ row.vm }}</el-link>
              <span style="font-size:11px;color:#909399;white-space:nowrap">（<span style="color:#10b981">{{ row.vm_on || 0 }}开</span>/<span style="color:#ef4444">{{ row.vm_off || 0 }}关</span>）</span>
            </template>
          </el-table-column>
          <el-table-column label="已备份" width="70" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goDept(row.dept_name, 'backup')" v-if="row.backup">{{ row.backup }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="已装椒图" width="80" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goDept(row.dept_name, 'qax')" v-if="row.qax">{{ row.qax }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="域名" width="80" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goDept(row.dept_name, 'domains')">{{ row.domain }}</el-link>
            </template>
          </el-table-column>
          <el-table-column label="信息系统" width="90" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goDept(row.dept_name, 'is')">{{ row.is_count }}</el-link>
            </template>
          </el-table-column>
          <el-table-column label="管理员" width="70" align="center">
            <template #default="{row}">{{ row.admin_count }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- ═══════════ 部门管理员：人员清单 ═══════════ -->
      <template v-if="authStore.isDeptAdmin && !authStore.isAdmin && data && data.members">
        <h3 class="section-title">本部门人员清单</h3>
        <el-table :data="data.members" stripe size="small">
          <el-table-column prop="name" label="姓名" width="80" />
          <el-table-column prop="gh" label="工号" width="90" />
          <el-table-column label="虚拟机" width="150" align="center">
            <template #default="{row}">
              <template v-if="row.vm">
                <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'vm')">{{ row.vm }}</el-link>
                <span style="font-size:11px;color:#909399;white-space:nowrap">（<span style="color:#10b981">{{ row.vm_on || 0 }}开</span>/<span style="color:#ef4444">{{ row.vm_off || 0 }}关</span>）</span>
              </template>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="域名" width="80" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'domains')" v-if="row.domain">{{ row.domain }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="信息系统" width="90" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'is')" v-if="row.is_count">{{ row.is_count }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="供应链" width="80" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'sc')" v-if="row.sc">{{ row.sc }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="已备份" width="70" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'backup')" v-if="row.backup">{{ row.backup }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="已装椒图" width="80" align="center">
            <template #default="{row}">
              <el-link type="primary" :underline="false" @click="goMemberAssets(row, 'qax')" v-if="row.qax">{{ row.qax }}</el-link>
              <span v-else>0</span>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- ═══════════ 通用：VM/域名/IS 统计 ═══════════ -->
      <template v-if="data">
        <h3 class="section-title" style="margin-top:24px">虚拟机</h3>
        <el-row :gutter="16" class="stat-row">
          <el-col :span="4">
            <div class="stat-card" @click="go('/sys/assets')">
              <div class="stat-value">{{ data.vm.total }}</div>
              <div class="stat-label">总数</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card highlight-green" @click="go('/sys/assets', { power_state: 'poweredOn' })">
              <div class="stat-value">{{ data.vm.power_on }}</div>
              <div class="stat-label">开机</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card highlight-red" @click="go('/sys/assets', { power_state: 'poweredOff' })">
              <div class="stat-value">{{ data.vm.power_off }}</div>
              <div class="stat-label">关机</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card highlight-blue" @click="go('/sys/assets', { has_backup: 'yes' })">
              <div class="stat-value">{{ data.vm.backed_up }}</div>
              <div class="stat-label">已备份</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="stat-card highlight-purple" @click="go('/sys/assets', { has_qax: 'yes' })">
              <div class="stat-value">{{ data.vm.qax_installed }}</div>
              <div class="stat-label">已装椒图</div>
            </div>
          </el-col>
        </el-row>
        <el-row :gutter="16" class="stat-row" style="margin-top:12px">
          <el-col :span="6">
            <div class="stat-card small" @click="go('/sys/assets', { claimed: 'yes', power_state: 'poweredOn' })">
              <div class="stat-value">{{ data.vm.claimed.on }}</div>
              <div class="stat-label">已认领-开机</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card small" @click="go('/sys/assets', { claimed: 'yes', power_state: 'poweredOff' })">
              <div class="stat-value">{{ data.vm.claimed.off }}</div>
              <div class="stat-label">已认领-关机</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card small" @click="go('/sys/assets', { claimed: 'no', power_state: 'poweredOn' })">
              <div class="stat-value">{{ data.vm.unclaimed.on }}</div>
              <div class="stat-label">待认领-开机</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-card small" @click="go('/sys/assets', { claimed: 'no', power_state: 'poweredOff' })">
              <div class="stat-value">{{ data.vm.unclaimed.off }}</div>
              <div class="stat-label">待认领-关机</div>
            </div>
          </el-col>
        </el-row>

        <h3 class="section-title" style="margin-top:24px">域名</h3>
        <el-row :gutter="16" class="stat-row">
          <el-col :span="8">
            <div class="stat-card" @click="go('/sys/assets', { tab: 'domains' })">
              <div class="stat-value">{{ data.domain.total }}</div>
              <div class="stat-label">域名总数</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card highlight-green" @click="go('/sys/assets', { tab: 'domains', claimed: 'yes' })">
              <div class="stat-value">{{ data.domain.claimed }}</div>
              <div class="stat-label">已认领</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card highlight-orange" @click="go('/sys/assets', { tab: 'domains', claimed: 'no' })">
              <div class="stat-value">{{ data.domain.unclaimed }}</div>
              <div class="stat-label">待认领</div>
            </div>
          </el-col>
        </el-row>

        <h3 class="section-title" style="margin-top:24px">信息系统</h3>
        <el-row :gutter="16" class="stat-row">
          <el-col :span="8">
            <div class="stat-card" @click="go('/sys/info-systems')">
              <div class="stat-value">{{ data.is.total }}</div>
              <div class="stat-label">信息系统总数</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card highlight-green" @click="go('/sys/info-systems', { claimed: 'yes' })">
              <div class="stat-value">{{ data.is.claimed }}</div>
              <div class="stat-label">已认领</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="stat-card highlight-orange" @click="go('/sys/info-systems', { claimed: 'no' })">
              <div class="stat-value">{{ data.is.unclaimed }}</div>
              <div class="stat-label">待认领</div>
            </div>
          </el-col>
        </el-row>

        <!-- ═══════════ IS 数据完整性 ═══════════ -->
        <h3 class="section-title" style="margin-top:24px">信息系统数据完整性</h3>
        <el-row :gutter="16" class="stat-row">
          <el-col :span="6" v-for="item in isCompItems" :key="item.key">
            <div class="comp-card" @click="go('/sys/info-systems')">
              <div class="comp-label">{{ item.label }}</div>
              <el-progress :percentage="item.value" :color="item.color" :stroke-width="14" />
            </div>
          </el-col>
        </el-row>

        <!-- ═══════════ SC 数据完整性 ═══════════ -->
        <h3 class="section-title" style="margin-top:24px">供应链数据完整性</h3>
        <el-row :gutter="16" class="stat-row">
          <el-col :span="6" v-for="(item, key) in data.sc_completeness" :key="key">
            <div class="comp-card" @click="go('/sys/supply-chain')">
              <div class="comp-label">{{ item.label }}</div>
              <el-progress :percentage="item.pct" :color="pctColor(item.pct)" :stroke-width="12" />
            </div>
          </el-col>
        </el-row>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getTaskOverview } from '@/api/task-overview'
import { Refresh } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)
const data = ref(null)

const isCompItems = computed(() => {
  if (!data.value?.is_completeness) return []
  const map = { system_name: '系统名称', system_type: '系统类型', sub_type: '子类型', domain: '域名', manager: '负责人', dept: '部门', djdj: '等保', vendor: '厂商' }
  return Object.entries(data.value.is_completeness).map(([k, v]) => ({
    key: k, label: map[k] || k, value: v,
    color: v >= 80 ? '#10b981' : v >= 50 ? '#f59e0b' : '#ef4444',
  }))
})

function pctColor(v) {
  return v >= 80 ? '#10b981' : v >= 50 ? '#f59e0b' : '#ef4444'
}

function go(path, query) {
  router.push({ path, ...(query ? { query } : {}) })
}

function goMemberAssets(row, type) {
  const q = { search: row.name }
  if (type === 'vm') go('/sys/assets', q)
  else if (type === 'domains') go('/sys/assets', { ...q, tab: 'domains' })
  else if (type === 'is') go('/sys/info-systems', q)
  else if (type === 'sc') go('/sys/supply-chain', q)
  else if (type === 'backup') go('/sys/assets', { search: row.name, has_backup: 'yes' })
  else if (type === 'qax') go('/sys/assets', { search: row.name, has_qax: 'yes' })
}

function goDept(deptName, type) {
  const query = { search: deptName }
  if (type === 'vm') go('/sys/assets', query)
  else if (type === 'domains') go('/sys/assets', { ...query, tab: 'domains' })
  else if (type === 'is') go('/sys/info-systems', query)
  else if (type === 'backup') go('/sys/assets', { search: deptName, has_backup: 'yes' })
  else if (type === 'qax') go('/sys/assets', { search: deptName, has_qax: 'yes' })
}

async function refresh() {
  loading.value = true
  try {
    data.value = await getTaskOverview()
  } catch { /* */ }
  finally { loading.value = false }
}

onMounted(refresh)
</script>

<style scoped>
.task-overview { max-width: 1400px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.page-header h2 { margin: 0; font-size: 20px; font-weight: 600; }
.section-title { font-size: 15px; font-weight: 600; color: var(--color-text); margin: 16px 0 12px; padding-left: 8px; border-left: 3px solid var(--color-primary); }

.stat-row { margin-bottom: 0; }
.stat-card {
  background: var(--color-bg-card); border-radius: 10px; padding: 20px 16px; text-align: center;
  border: 1px solid var(--color-border); cursor: pointer; transition: all .2s;
}
.stat-card:hover { border-color: var(--color-primary); box-shadow: 0 2px 12px rgba(99,102,241,.15); transform: translateY(-1px); }
.stat-card.small { padding: 14px 12px; }
.stat-card .stat-value { font-size: 28px; font-weight: 700; color: var(--color-text); }
.stat-card.small .stat-value { font-size: 22px; }
.stat-card .stat-label { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; }

.highlight-green .stat-value { color: #10b981; }
.highlight-red .stat-value { color: #ef4444; }
.highlight-blue .stat-value { color: #3b82f6; }
.highlight-purple .stat-value { color: #8b5cf6; }
.highlight-orange .stat-value { color: #f59e0b; }

.comp-card {
  background: var(--color-bg-card); border-radius: 10px; padding: 16px;
  border: 1px solid var(--color-border); cursor: pointer; transition: all .2s;
}
.comp-card:hover { border-color: var(--color-primary); }
.comp-card .comp-label { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 8px; }
</style>
