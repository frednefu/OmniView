<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h2>仪表盘</h2>
        <p class="page-desc">全栈资源概览 · 交换机 / vCenter / F5 / ZDNS / 椒图</p>
      </div>
      <el-button text @click="refreshAll" :loading="refreshing">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- ═══════════ 普通用户：个人统计卡片 ═══════════ -->
    <template v-if="!authStore.isAdmin">
      <el-row :gutter="16" class="stat-row">
        <el-col :span="6">
          <div class="stat-card" @click="go('/sys/assets')">
            <div class="stat-icon" style="background:linear-gradient(135deg,#6366f1,#818cf8)"><el-icon :size="22"><Monitor /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ personal.my_vms }}</div><div class="stat-title">我的虚拟机</div></div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card" @click="go('/sys/assets')">
            <div class="stat-icon" style="background:linear-gradient(135deg,#10b981,#34d399)"><el-icon :size="22"><Connection /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ personal.my_domains }}</div><div class="stat-title">我的域名</div></div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card" @click="go('/sys/info-systems')">
            <div class="stat-icon" style="background:linear-gradient(135deg,#f59e0b,#fbbf24)"><el-icon :size="22"><Discount /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ personal.my_systems }}</div><div class="stat-title">我的信息系统</div></div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card" @click="go('/subnets')">
            <div class="stat-icon" style="background:linear-gradient(135deg,#ef4444,#f87171)"><el-icon :size="22"><Grid /></el-icon></div>
            <div class="stat-info"><div class="stat-value">{{ personal.my_subnets }}</div><div class="stat-title">我的地址段</div></div>
          </div>
        </el-col>
      </el-row>
      <!-- 个人子网 IP 利用率 -->
      <el-card shadow="hover" class="chart-card" style="margin-top:16px">
        <template #header>我的地址段 IP 利用率</template>
        <div v-if="personal.subnet_utilization && personal.subnet_utilization.length>0" ref="personalBarRef" class="chart-container"></div>
        <el-empty v-else description="暂无地址段数据" />
      </el-card>
      <!-- 已占用 IP 对话框 -->
      <el-dialog v-model="personalOccupiedVisible" :title="'已占用 IP - '+personalOccupiedCidr" width="800px">
        <el-table :data="personalOccupiedData" v-loading="personalOccupiedLoading" stripe size="small" max-height="400">
          <el-table-column prop="ip" label="IP 地址" width="160" />
          <el-table-column prop="mac" label="MAC 地址" width="160" />
          <el-table-column prop="vm_name" label="关联 VM" min-width="140" />
          <el-table-column prop="domain" label="关联域名" min-width="160" />
        </el-table>
        <el-pagination v-if="personalOccupiedTotal>20" v-model:current-page="personalOccupiedPage" :page-size="20" :total="personalOccupiedTotal" layout="prev,pager,next" small @current-change="(p)=>{personalOccupiedPage=p;fetchPersonalOccupiedIps()}" style="margin-top:10px;justify-content:center"/>
      </el-dialog>
    </template>

    <!-- ═══════════ 管理员：统计卡片 ═══════════ -->
    <template v-else>
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <div class="stat-card" @click="go('/switches')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #6366f1, #818cf8);">
            <el-icon :size="22"><Monitor /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.switch_count }}</div>
            <div class="stat-title">活跃交换机</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" @click="openIpMacDialog('ip')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #10b981, #34d399);">
            <el-icon :size="22"><Connection /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_ips }}</div>
            <div class="stat-title">唯一 IP 地址</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" @click="openIpMacDialog('mac')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #f59e0b, #fbbf24);">
            <el-icon :size="22"><Discount /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total_macs }}</div>
            <div class="stat-title">MAC 地址</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" @click="go('/subnets')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #ef4444, #f87171);">
            <el-icon :size="22"><Grid /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.subnet_count }}</div>
            <div class="stat-title">管理子网</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="stat-row stat-flex-row">
      <div class="stat-card" @click="go('/vcenters')">
        <div class="stat-icon" style="background: linear-gradient(135deg, #06b6d4, #22d3ee);">
          <el-icon :size="22"><Cloudy /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.vcenter.vcenter_count }}</div>
          <div class="stat-title">vCenter</div>
        </div>
      </div>
      <div class="stat-card" @click="openVMDialog">
        <div class="stat-icon" style="background: linear-gradient(135deg, #8b5cf6, #a78bfa);">
          <el-icon :size="22"><Cpu /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.vcenter.vm_total }}<span class="stat-sub"> / {{ stats.vcenter.vm_powered_on }}开 / {{ stats.vcenter.vm_powered_off }}关</span></div>
          <div class="stat-title">虚拟机</div>
        </div>
      </div>
      <div class="stat-card" @click="go('/f5')">
        <div class="stat-icon" style="background: linear-gradient(135deg, #f97316, #fb923c);">
          <el-icon :size="22"><Connection /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.f5.device_count }}</div>
          <div class="stat-title">F5 设备</div>
        </div>
      </div>
      <div class="stat-card" @click="go('/zdns')">
        <div class="stat-icon" style="background: linear-gradient(135deg, #14b8a6, #2dd4bf);">
          <el-icon :size="22"><Link /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.zdns.device_count }}</div>
          <div class="stat-title">ZDNS 设备</div>
        </div>
      </div>
      <div class="stat-card" @click="go('/qax')">
        <div class="stat-icon" style="background: linear-gradient(135deg, #ec4899, #f472b6);">
          <el-icon :size="22"><Monitor /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ stats.qax.server_count }}</div>
          <div class="stat-title">椒图服务器</div>
        </div>
      </div>
    </div>

    <el-row :gutter="16" class="stat-row">
      <el-col :span="8">
        <div class="stat-card" @click="openAssetDetail('domains')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #6366f1, #a78bfa);">
            <el-icon :size="22"><Link /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.asset.域名总数 }}</div>
            <div class="stat-title">域名总数</div>
            <div class="stat-detail">ZDNS {{ stats.asset.zdns域名 }} · F5 {{ stats.asset.f5域名 }}</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card" @click="openAssetDetail('public_services')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #10b981, #6ee7b7);">
            <el-icon :size="22"><Monitor /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.asset.公网服务 }}</div>
            <div class="stat-title">公网服务</div>
            <div class="stat-detail">公网IP:端口</div>
          </div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="stat-card" @click="openAssetDetail('internal_services')">
          <div class="stat-icon" style="background: linear-gradient(135deg, #f59e0b, #fcd34d);">
            <el-icon :size="22"><Connection /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.asset.内网服务 }}</div>
            <div class="stat-title">内网服务</div>
            <div class="stat-detail">内网IP:端口</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- ═══════════ 图表第一行 ═══════════ -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="6">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>VM 开关机分布</strong></template>
          <div v-if="vmDonutEmpty" class="empty-chart"><el-empty description="暂无 VM 数据" :image-size="50" /></div>
          <div v-else ref="vmDonutRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>DNS 记录类型</strong></template>
          <div v-if="dnsPieEmpty" class="empty-chart"><el-empty description="暂无 DNS 数据" :image-size="50" /></div>
          <div v-else ref="dnsPieRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>F5 Pool 成员状态</strong></template>
          <div v-if="f5DonutEmpty" class="empty-chart"><el-empty description="暂无 F5 数据" :image-size="50" /></div>
          <div v-else ref="f5DonutRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>各数据源扫描次数</strong></template>
          <div v-if="scanBarEmpty" class="empty-chart"><el-empty description="暂无扫描数据" :image-size="50" /></div>
          <div v-else ref="scanBarRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 图表第二行 ═══════════ -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="14">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <strong>IP 利用率</strong>
              <span class="card-hint" v-if="subnets.length">{{ subnets.length }} 个地址段 · 点击柱子查看已占用 IP</span>
            </div>
          </template>
          <div v-if="subnets.length === 0" class="empty-chart">
            <el-empty description="暂无地址段数据" :image-size="60">
              <el-button type="primary" size="small" @click="go('/subnets')">管理地址段</el-button>
            </el-empty>
          </div>
          <div v-else ref="subnetBarRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>vCenter 资源统计</strong></template>
          <div v-if="vcenterResourceEmpty" class="empty-chart"><el-empty description="暂无 vCenter 数据" :image-size="50" /></div>
          <div v-else ref="vcResourceRef" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 图表第三行：OS 分布 ═══════════ -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>椒图 OS 分布</strong></template>
          <div v-if="qaxOSEmpty" class="empty-chart"><el-empty description="暂无椒图数据" :image-size="50" /></div>
          <div v-else ref="qaxOSRef" class="chart-box-wide"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>vCenter VM OS 分布</strong></template>
          <div v-if="vcOSEmpty" class="empty-chart"><el-empty description="暂无 VM OS 数据" :image-size="50" /></div>
          <div v-else ref="vcOSRef" class="chart-box-wide"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 图表第四行：CPU 核数 + 内存分布 ═══════════ -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>vCenter VM CPU 核数分布</strong></template>
          <div v-if="vcCpuEmpty" class="empty-chart"><el-empty description="暂无 VM CPU 数据" :image-size="50" /></div>
          <div v-else ref="vcCpuRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>vCenter VM 内存容量分布</strong></template>
          <div v-if="vcMemEmpty" class="empty-chart"><el-empty description="暂无 VM 内存数据" :image-size="50" /></div>
          <div v-else ref="vcMemRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 图表第五行：ESXi CPU 类型 + 存储容量 ═══════════ -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>ESXi CPU 类型分布</strong></template>
          <div v-if="esxiCpuEmpty" class="empty-chart"><el-empty description="暂无 ESXi 数据" :image-size="50" /></div>
          <div v-else ref="esxiCpuRef" class="chart-box-wide"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="chart-card">
          <template #header><strong>存储容量（按类型）</strong></template>
          <div v-if="dsStorageEmpty" class="empty-chart"><el-empty description="暂无存储数据" :image-size="50" /></div>
          <div v-else ref="dsStorageRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 底部 ═══════════ -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="hover" class="available-card">
          <template #header><strong>可用 IP 查询</strong></template>
          <el-form label-width="0" class="ip-form">
            <el-select v-model="selectedSubnetId" placeholder="选择地址段查看可用 IP..." @change="fetchAvailableIps" filterable>
              <el-option v-for="s in subnets" :key="s.subnet_id"
                :label="`${s.name} (${s.subnet_cidr})`" :value="s.subnet_id" />
            </el-select>
          </el-form>
          <el-table :data="availableIps" max-height="280" v-loading="loadingIps" stripe size="small">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="ip" label="IP 地址" />
            <template #empty>
              <span v-if="selectedSubnetId && !loadingIps" style="color: var(--color-text-muted);">该地址段暂无可用 IP</span>
            </template>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="summary-card">
          <template #header><strong>扫描 & 变更摘要</strong></template>
          <div class="summary-grid">
            <div class="summary-item success">
              <div class="summary-num">{{ stats.last_scan_success }}</div>
              <div class="summary-label">扫描成功</div>
            </div>
            <div class="summary-item danger">
              <div class="summary-num">{{ stats.last_scan_failed }}</div>
              <div class="summary-label">扫描失败</div>
            </div>
            <div class="summary-item info">
              <div class="summary-num">{{ stats.last_scan_total }}</div>
              <div class="summary-label">总扫描次数</div>
            </div>
            <div class="summary-item primary">
              <div class="summary-num">{{ stats.last_scan_total > 0 ? Math.round(stats.last_scan_success / stats.last_scan_total * 100) : 0 }}%</div>
              <div class="summary-label">扫描成功率</div>
            </div>
          </div>
          <div class="summary-source" v-if="stats.scan_by_source.length">
            <div class="source-row" v-for="s in stats.scan_by_source" :key="s.source_type">
              <span>{{ s.source_label }}</span>
              <span class="source-count">{{ s.count }} 次</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ═══════════ 子网已占用 IP 对话框 ═══════════ -->
    <el-dialog v-model="occupiedDialogVisible" :title="`已占用 IP — ${occupiedData.subnet_name || ''}`" width="900px" @closed="Object.assign(occupiedData, { subnet_cidr: '', subnet_name: '', occupied: [], total: 0 })">
      <div class="dialog-search-bar" v-if="occupiedData.total > 0 || occupiedSearch">
        <el-input v-model="occupiedSearch" placeholder="搜索 IP、MAC、虚拟机名称、域名..." clearable style="width:380px"
          @keyup.enter="occupiedPage=1;fetchOccupiedIps(occupiedSubnetId)"
          @clear="occupiedPage=1;fetchOccupiedIps(occupiedSubnetId)" />
      </div>
      <div v-if="occupiedData.occupied.length === 0" style="text-align:center;padding:20px;color:var(--color-text-muted);">该子网暂无已占用 IP 数据</div>
      <el-table v-else :data="occupiedData.occupied" stripe size="small" max-height="400">
        <el-table-column prop="ip" label="IP 地址" width="150" />
        <el-table-column prop="mac" label="MAC 地址" width="160" />
        <el-table-column prop="vm_name" label="虚拟机名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="domain" label="域名" min-width="200" show-overflow-tooltip />
      </el-table>
      <div class="occupied-pagination" v-if="occupiedData.total > occupiedPageSize">
        <el-pagination
          v-model:current-page="occupiedPage"
          :page-size="occupiedPageSize"
          :total="occupiedData.total"
          layout="prev, pager, next"
          small
          @current-change="(p) => { occupiedPage = p; fetchOccupiedIps(occupiedSubnetId) }"
        />
      </div>
    </el-dialog>

    <!-- ═══════════ 资产明细对话框（域名 / 公网服务 / 内网服务） ═══════════ -->
    <el-dialog v-model="showAssetDetailDialog" :title="assetDetailTitle" width="700px" @closed="assetDetailItems=[];assetDetailSearch=''">
      <div class="dialog-search-bar" v-if="assetDetailItems.length > 0 || assetDetailSearch">
        <el-input v-model="assetDetailSearch" placeholder="搜索..." clearable style="width:300px"
          @keyup.enter="fetchAssetDetailItems" @clear="fetchAssetDetailItems" />
      </div>
      <div v-if="assetDetailItems.length === 0 && !assetDetailLoading" style="text-align:center;padding:20px;color:var(--color-text-muted);">暂无数据</div>
      <el-table v-else :data="filteredAssetItems" stripe size="small" max-height="400" v-loading="assetDetailLoading">
        <template v-if="assetDetailType === 'domains'">
          <el-table-column prop="domain_name" label="域名" min-width="350" show-overflow-tooltip />
          <el-table-column label="来源" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.source && row.source.includes('ZDNS')" type="primary" size="small">ZDNS</el-tag>
              <el-tag v-if="row.source && row.source.includes('F5')" type="success" size="small" :style="row.source.includes('ZDNS')?'margin-left:4px':''">F5</el-tag>
            </template>
          </el-table-column>
        </template>
        <template v-else>
          <el-table-column prop="ip" label="IP 地址" width="180" />
          <el-table-column prop="port" label="端口" width="100" />
        </template>
      </el-table>
    </el-dialog>

    <!-- ═══════════ 虚拟机明细对话框 ═══════════ -->
    <el-dialog v-model="showVMDialog" :title="`虚拟机明细（共 ${vmTotal} 台）`" width="95%" @closed="vmSearch='';vmPage=1">
      <div class="dialog-search-bar">
        <el-input v-model="vmSearch" placeholder="搜索名称、IP、MAC、OS、集群、主机、网络、文件夹..." clearable style="width:380px"
          @keyup.enter="vmPage=1;fetchVMs()" @clear="vmPage=1;fetchVMs()" />
      </div>
      <el-table :data="vmList" stripe v-loading="loadingVM" size="small" max-height="500">
        <el-table-column prop="vm_name" label="虚拟机名称" min-width="180" fixed show-overflow-tooltip />
        <el-table-column prop="power_state" label="电源" width="80">
          <template #default="{ row }">
            <el-tag :type="row.power_state==='poweredOn'?'success':'info'" size="small">
              {{ row.power_state==='poweredOn'?'开机':row.power_state==='poweredOff'?'关机':row.power_state }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP 地址" min-width="140" show-overflow-tooltip />
        <el-table-column prop="mac_address" label="MAC 地址" min-width="140" show-overflow-tooltip />
        <el-table-column prop="os_name" label="操作系统" min-width="140" show-overflow-tooltip />
        <el-table-column prop="cpu_count" label="CPU" width="55" />
        <el-table-column prop="memory_gb" label="内存(GB)" width="80" />
        <el-table-column prop="datacenter" label="数据中心" min-width="110" show-overflow-tooltip />
        <el-table-column prop="cluster" label="集群" min-width="110" show-overflow-tooltip />
        <el-table-column prop="esxi_host" label="ESXi 主机" min-width="130" show-overflow-tooltip />
        <el-table-column prop="network_name" label="网络" min-width="110" show-overflow-tooltip />
        <el-table-column prop="vlan_id" label="VLAN" width="70" />
        <el-table-column prop="resource_pool" label="资源池" min-width="100" show-overflow-tooltip />
        <el-table-column prop="vm_folder" label="文件夹" min-width="110" show-overflow-tooltip />
      </el-table>
      <div class="occupied-pagination" v-if="vmTotal > vmSize">
        <el-pagination
          v-model:current-page="vmPage"
          :page-size="vmSize"
          :total="vmTotal"
          layout="total, prev, pager, next"
          small
          @current-change="(p) => { vmPage = p; fetchVMs() }"
        />
      </div>
    </el-dialog>

    <!-- ═══════════ IP/MAC 明细对话框 ═══════════ -->
    <el-dialog v-model="showIpMacDialog" :title="ipMacDialogTitle" width="500px">
      <div class="dialog-search-bar" v-if="ipMacList.length > 0 || ipMacSearch">
        <el-input v-model="ipMacSearch" :placeholder="ipMacType==='ip'?'搜索 IP...':'搜索 MAC...'" clearable style="width:280px"
          @keyup.enter="ipMacPage=1;fetchIpMacList()" @clear="ipMacPage=1;fetchIpMacList()" />
      </div>
      <el-table :data="ipMacList" v-loading="loadingIpMac" stripe size="small" max-height="400">
        <el-table-column prop="value" :label="ipMacType==='ip'?'IP 地址':'MAC 地址'" min-width="300" show-overflow-tooltip />
      </el-table>
      <div class="occupied-pagination" v-if="ipMacTotal > ipMacSize">
        <el-pagination
          v-model:current-page="ipMacPage"
          :page-size="ipMacSize"
          :total="ipMacTotal"
          layout="prev, pager, next"
          small
          @current-change="(p) => { ipMacPage = p; fetchIpMacList() }"
        />
      </div>
    </el-dialog>
  </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import * as echarts from 'echarts'
import api from '@/api'

const authStore = useAuthStore()

const router = useRouter()

// ── 状态 ──
const stats = reactive({
  switch_count: 0, total_ips: 0, total_macs: 0, subnet_count: 0,
  vcenter: { vcenter_count: 0, vm_total: 0, vm_powered_on: 0, vm_powered_off: 0, total_cpu_cores: 0, total_memory_gb: 0, per_vcenter: [], os_distribution: [], cpu_cores_distribution: [], memory_distribution: [], esxi_cpu_types: [], datastore_total_capacity_gb: 0, datastore_total_free_gb: 0, datastore_by_type: [] },
  f5: { device_count: 0, vs_count: 0, pool_count: 0, rule_count: 0, app_map_count: 0, pool_member_up: 0, pool_member_down: 0 },
  zdns: { device_count: 0, record_count: 0, domain_map_count: 0, ipv4_count: 0, ipv6_count: 0, internal_count: 0, external_count: 0, record_types: [] },
  qax: { device_count: 0, server_count: 0, os_distribution: [] },
  asset: { 域名总数: 0, zdns域名: 0, f5域名: 0, 公网服务: 0, 内网服务: 0 },
  scan_by_source: [],
  last_scan_total: 0, last_scan_success: 0, last_scan_failed: 0,
})
const personal = reactive({ my_vms: 0, my_domains: 0, my_systems: 0, my_subnets: 0, subnet_utilization: [] })
const personalBarRef = ref(null)
const personalOccupiedVisible = ref(false), personalOccupiedLoading = ref(false)
const personalOccupiedCidr = ref(''), personalOccupiedData = ref([])
const personalOccupiedTotal = ref(0), personalOccupiedPage = ref(1)
let personalOccupiedSubnetId = null

const subnets = ref([])
const selectedSubnetId = ref(null)
const availableIps = ref([])
const loadingIps = ref(false)
const refreshing = ref(false)

// ── 图表引用 ──
const vmDonutRef = ref(null)
const dnsPieRef = ref(null)
const f5DonutRef = ref(null)
const scanBarRef = ref(null)
const subnetBarRef = ref(null)
const vcResourceRef = ref(null)
const qaxOSRef = ref(null)
const vcOSRef = ref(null)
const vcCpuRef = ref(null)
const vcMemRef = ref(null)
const esxiCpuRef = ref(null)
const dsStorageRef = ref(null)

const vmDonutEmpty = computed(() => stats.vcenter.vm_total === 0)
const dnsPieEmpty = computed(() => stats.zdns.record_types.length === 0)
const f5DonutEmpty = computed(() => (stats.f5.pool_member_up + stats.f5.pool_member_down) === 0)
const scanBarEmpty = computed(() => stats.scan_by_source.length === 0)
const vcenterResourceEmpty = computed(() => stats.vcenter.per_vcenter.length === 0)
const qaxOSEmpty = computed(() => stats.qax.os_distribution.length === 0)
const vcOSEmpty = computed(() => stats.vcenter.os_distribution.length === 0)
const vcCpuEmpty = computed(() => stats.vcenter.cpu_cores_distribution.length === 0)
const vcMemEmpty = computed(() => stats.vcenter.memory_distribution.length === 0)
const esxiCpuEmpty = computed(() => stats.vcenter.esxi_cpu_types.length === 0)
const dsStorageEmpty = computed(() => stats.vcenter.datastore_by_type.length === 0)

// ── 子网已占用 IP 对话框 ──
const occupiedDialogVisible = ref(false)
const occupiedSubnetId = ref(null)
const occupiedPage = ref(1)
const occupiedPageSize = ref(50)
const occupiedSearch = ref('')
const occupiedData = reactive({ subnet_cidr: '', subnet_name: '', occupied: [], total: 0 })

// ── 资产明细对话框 ──
const showAssetDetailDialog = ref(false)
const assetDetailType = ref('')
const assetDetailTitle = ref('')
const assetDetailItems = ref([])
const assetDetailSearch = ref('')
const assetDetailLoading = ref(false)

const filteredAssetItems = computed(() => {
  if (!assetDetailSearch.value) return assetDetailItems.value
  const q = assetDetailSearch.value.toLowerCase()
  return assetDetailItems.value.filter(item => {
    if (assetDetailType.value === 'domains') {
      return (item.domain_name || '').toLowerCase().includes(q) || (item.source || '').toLowerCase().includes(q)
    }
    return (item.ip || '').toLowerCase().includes(q) || String(item.port || '').includes(q)
  })
})

async function openAssetDetail(type) {
  assetDetailType.value = type
  assetDetailSearch.value = ''
  assetDetailItems.value = []
  const titles = { domains: '域名明细', public_services: '公网服务明细', internal_services: '内网服务明细' }
  assetDetailTitle.value = titles[type] || ''
  showAssetDetailDialog.value = true
  await fetchAssetDetailItems()
}

async function fetchAssetDetailItems() {
  assetDetailLoading.value = true
  try {
    const { data } = await api.get('/dashboard/asset-details', {
      params: { type: assetDetailType.value, search: assetDetailSearch.value }
    })
    assetDetailItems.value = data.items || []
  } catch { /* handled */ }
  finally { assetDetailLoading.value = false }
}

// ── IP/MAC 明细对话框 ──
const showIpMacDialog = ref(false)
const ipMacType = ref('ip')
const ipMacDialogTitle = computed(() => ipMacType.value === 'ip' ? '唯一 IP 地址明细（去重）' : 'MAC 地址明细（去重）')
const ipMacList = ref([])
const ipMacPage = ref(1)
const ipMacSize = ref(50)
const ipMacTotal = ref(0)
const ipMacSearch = ref('')
const loadingIpMac = ref(false)

function openIpMacDialog(type) {
  ipMacType.value = type
  ipMacSearch.value = ''
  ipMacPage.value = 1
  showIpMacDialog.value = true
  fetchIpMacList()
}

// ── 虚拟机明细对话框 ──
const showVMDialog = ref(false)
const vmList = ref([])
const vmSearch = ref('')
const vmTotal = ref(0)
const vmPage = ref(1)
const vmSize = ref(30)
const loadingVM = ref(false)

function openVMDialog() {
  vmSearch.value = ''
  vmPage.value = 1
  showVMDialog.value = true
  fetchVMs()
}

async function fetchVMs() {
  loadingVM.value = true
  try {
    const { data } = await api.get('/dashboard/vm-details', {
      params: { page: vmPage.value, size: vmSize.value, search: vmSearch.value }
    })
    vmList.value = data.items || []
    vmTotal.value = data.total || 0
  } catch { /* handled */ }
  finally { loadingVM.value = false }
}

// ── 图表实例 ──
let vmDonutChart, dnsPieChart, f5DonutChart, scanBarChart, subnetBarChart, vcResourceChart, personalBarChart
let qaxOSChart, vcOSChart, vcCpuChart, vcMemChart, esxiCpuChart, dsStorageChart

function go(path) {
  router.push(path)
}

// ── 数据获取 ──
async function fetchStats() {
  try {
    const { data } = await api.get('/dashboard/stats')
    Object.assign(stats, data)
    await nextTick()
    renderAllCharts()
  } catch { /* handled by interceptor */ }
}

async function fetchUtilization() {
  try {
    const { data } = await api.get('/dashboard/subnet-utilization')
    subnets.value = data
    await nextTick()
    renderSubnetBar()
  } catch { /* handled */ }
}

async function fetchAvailableIps() {
  if (!selectedSubnetId.value) return
  loadingIps.value = true
  try {
    const { data } = await api.get('/dashboard/available-ips', {
      params: { subnet_id: selectedSubnetId.value, limit: 100 }
    })
    availableIps.value = data.available_ips.map(ip => ({ ip }))
  } catch { /* handled */ }
  finally { loadingIps.value = false }
}

async function fetchOccupiedIps(subnetId) {
  try {
    const { data } = await api.get('/dashboard/subnet-occupied-ips', {
      params: { subnet_id: subnetId, page: occupiedPage.value, size: occupiedPageSize.value, search: occupiedSearch.value }
    })
    Object.assign(occupiedData, data)
  } catch { /* handled */ }
}

async function fetchIpMacList() {
  loadingIpMac.value = true
  try {
    const { data } = await api.get('/dashboard/ip-mac-list', {
      params: { type: ipMacType.value, page: ipMacPage.value, size: ipMacSize.value, search: ipMacSearch.value }
    })
    ipMacList.value = data.items || []
    ipMacTotal.value = data.total || 0
  } catch { /* handled */ }
  finally { loadingIpMac.value = false }
}

async function fetchPersonal() {
  try {
    const { data } = await api.get('/dashboard/personal')
    personal.my_vms = data.my_vms; personal.my_domains = data.my_domains
    personal.my_systems = data.my_systems; personal.my_subnets = data.my_subnets
    personal.subnet_utilization = data.subnet_utilization || []
    nextTick(() => renderPersonalBar())
  } catch {}
}
function renderPersonalBar() {
  const el = personalBarRef.value; if (!el) return
  const data = personal.subnet_utilization; if (!data.length) return
  if (!personalBarChart) personalBarChart = echarts.init(el)
  personalBarChart.off('click')
  personalBarChart.on('click', (params) => {
    if (params.componentType === 'series') {
      const item = data[params.dataIndex]
      if (item) {
        personalOccupiedSubnetId = item.subnet_id
        personalOccupiedCidr.value = item.subnet_cidr
        personalOccupiedPage.value = 1
        fetchPersonalOccupiedIps()
        personalOccupiedVisible.value = true
      }
    }
  })
  const names = data.map(d => (d.name||d.subnet_cidr||'')+'\n'+d.subnet_cidr)
  const used = data.map(d => d.used_ips)
  const free = data.map(d => d.free_ips)
  personalBarChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: function(params) {
        const el = data[params[0].dataIndex]
        return '<b>'+el.name+'</b> ('+el.subnet_cidr+')<br/>已用: <b style=\"color:#ef4444\">'+el.used_ips+'</b> | 可用: <b style=\"color:#10b981\">'+el.free_ips+'</b> | 总计: '+el.total_ips+'<br/>利用率: '+el.utilization_pct+'%<br/><span style=\"color:#94a3b8;font-size:11px\">点击查看已占用 IP</span>'
      }
    },
    legend: { data: ['已用','可用'], itemWidth: 12, itemHeight: 12, itemGap: 20, textStyle: { color: '#64748b', fontSize: 13 }, bottom: 0 },
    grid: { left: '3%', right: '4%', top: '3%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: names, axisLabel: { interval: 0, rotate: 30, fontSize: 11, color: '#64748b' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', name: 'IP 数量', nameTextStyle: { color: '#94a3b8', fontSize: 12 }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [
      { name: '已用', type: 'bar', stack: 'total', data: used, barWidth: 28, itemStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'#f87171'},{offset:1,color:'#ef4444'}]) } },
      { name: '可用', type: 'bar', stack: 'total', data: free, barWidth: 28, itemStyle: { borderRadius: [6,6,0,0], color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'#34d399'},{offset:1,color:'#10b981'}]) } },
    ]
  }, { notMerge: true })
}
async function fetchPersonalOccupiedIps() {
  personalOccupiedLoading.value = true
  try {
    const { data } = await api.get('/dashboard/subnet-occupied-ips', {
      params: { subnet_id: personalOccupiedSubnetId, page: personalOccupiedPage.value, size: 20 }
    })
    personalOccupiedData.value = data.occupied; personalOccupiedTotal.value = data.total
  } catch {} finally { personalOccupiedLoading.value = false }
}

async function refreshAll() {
  refreshing.value = true
  const tasks = [fetchStats(), fetchUtilization()]
  if (!authStore.isAdmin) tasks.push(fetchPersonal())
  await Promise.all(tasks)
  refreshing.value = false
}

// ── 图表渲染 ──
function renderAllCharts() {
  renderVmDonut()
  renderDnsPie()
  renderF5Donut()
  renderScanBar()
  renderVcResource()
  renderQaxOS()
  renderVcOS()
  renderVcCpu()
  renderVcMem()
  renderEsxiCpu()
  renderDsStorage()
}

function renderVmDonut() {
  if (vmDonutEmpty.value || !vmDonutRef.value) return
  if (!vmDonutChart) vmDonutChart = echarts.init(vmDonutRef.value)
  const { vm_powered_on, vm_powered_off, vm_total } = stats.vcenter
  vmDonutChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['55%', '78%'], center: ['50%', '55%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: [
        { value: vm_powered_on, name: '开机', itemStyle: { color: '#10b981' } },
        { value: vm_powered_off, name: '关机', itemStyle: { color: '#f59e0b' } },
      ],
    }],
    graphic: [{
      type: 'text', left: 'center', top: '40%',
      style: { text: vm_total, textAlign: 'center', fontSize: 20, fontWeight: 700, fill: '#1e293b' },
    }, {
      type: 'text', left: 'center', top: '54%',
      style: { text: '总计', textAlign: 'center', fontSize: 11, fill: '#94a3b8' },
    }],
  }, { notMerge: true })
}

function renderDnsPie() {
  if (dnsPieEmpty.value || !dnsPieRef.value) return
  if (!dnsPieChart) dnsPieChart = echarts.init(dnsPieRef.value)
  const types = stats.zdns.record_types
  const colors = { A: '#6366f1', AAAA: '#06b6d4', CNAME: '#f59e0b', PTR: '#10b981', NS: '#8b5cf6', MX: '#f97316', TXT: '#14b8a6', SPF: '#ec4899', SRV: '#84cc16' }
  const data = types.map(t => ({ value: t.count, name: t.record_type, itemStyle: { color: colors[t.record_type] || '#94a3b8' } }))
  dnsPieChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['0%', '68%'], center: ['50%', '55%'],
      itemStyle: { borderRadius: 3, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, position: 'outside', fontSize: 10, formatter: '{b}\n{d}%' },
      data: data.slice(0, 6),
    }],
  }, { notMerge: true })
}

function renderF5Donut() {
  if (f5DonutEmpty.value || !f5DonutRef.value) return
  if (!f5DonutChart) f5DonutChart = echarts.init(f5DonutRef.value)
  const { pool_member_up, pool_member_down } = stats.f5
  const total = pool_member_up + pool_member_down
  f5DonutChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['55%', '78%'], center: ['50%', '55%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: [
        { value: pool_member_up, name: 'UP', itemStyle: { color: '#10b981' } },
        { value: pool_member_down, name: 'DOWN', itemStyle: { color: '#ef4444' } },
      ],
    }],
    graphic: [{
      type: 'text', left: 'center', top: '40%',
      style: { text: total, textAlign: 'center', fontSize: 20, fontWeight: 700, fill: '#1e293b' },
    }, {
      type: 'text', left: 'center', top: '54%',
      style: { text: '成员总数', textAlign: 'center', fontSize: 11, fill: '#94a3b8' },
    }],
  }, { notMerge: true })
}

function renderScanBar() {
  if (scanBarEmpty.value || !scanBarRef.value) return
  if (!scanBarChart) scanBarChart = echarts.init(scanBarRef.value)
  const data = stats.scan_by_source
  const colors = { switch: '#06b6d4', vcenter: '#f59e0b', f5: '#10b981', zdns: '#6366f1', zdns_ip: '#8b5cf6', qax: '#ef4444' }
  scanBarChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', top: '5%', bottom: '5%', containLabel: true },
    xAxis: { type: 'category', data: data.map(d => d.source_label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', name: '次', nameTextStyle: { fontSize: 10, color: '#94a3b8' }, axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [{
      type: 'bar', data: data.map(d => ({ value: d.count, itemStyle: { color: colors[d.source_type] || '#94a3b8', borderRadius: [6, 6, 0, 0] } })),
      barWidth: 32,
    }],
  }, { notMerge: true })
}

function renderSubnetBar() {
  if (!subnetBarRef.value || subnets.value.length === 0) return
  if (!subnetBarChart) {
    subnetBarChart = echarts.init(subnetBarRef.value)
  }
  subnetBarChart.off('click')
  subnetBarChart.on('click', (params) => {
    if (params.componentType === 'series') {
      const item = subnets.value[params.dataIndex]
      if (item) {
        occupiedSubnetId.value = item.subnet_id
        occupiedPage.value = 1
        occupiedSearch.value = ''
        fetchOccupiedIps(item.subnet_id)
        occupiedDialogVisible.value = true
      }
    }
  })

  const data = subnets.value
  const names = data.map(d => d.name + '\n' + d.subnet_cidr)
  const used = data.map(d => d.used_ips)
  const free = data.map(d => d.free_ips)

  subnetBarChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: function (params) {
        const el = data[params[0].dataIndex]
        return `<b>${el.name}</b> (${el.subnet_cidr})<br/>已用: <b style="color:#ef4444">${el.used_ips}</b> | 可用: <b style="color:#10b981">${el.free_ips}</b> | 总计: ${el.total_ips}<br/>利用率: ${el.utilization_pct}%<br/><span style="color:#94a3b8;font-size:11px">点击查看已占用 IP</span>`
      }
    },
    legend: { data: ['已用', '可用'], itemWidth: 12, itemHeight: 12, itemGap: 20, textStyle: { color: '#64748b', fontSize: 13 }, bottom: 0 },
    grid: { left: '3%', right: '4%', top: '3%', bottom: '12%', containLabel: true },
    xAxis: { type: 'category', data: names, axisLabel: { interval: 0, rotate: 30, fontSize: 11, color: '#64748b' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', name: 'IP 数量', nameTextStyle: { color: '#94a3b8', fontSize: 12 }, axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [
      { name: '已用', type: 'bar', stack: 'total', data: used, barWidth: 28, itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#f87171' }, { offset: 1, color: '#ef4444' }]) } },
      { name: '可用', type: 'bar', stack: 'total', data: free, barWidth: 28, itemStyle: { borderRadius: [6, 6, 0, 0], color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#10b981' }]) } },
    ],
  }, { notMerge: true })
}

function renderVcResource() {
  if (vcenterResourceEmpty.value || !vcResourceRef.value) return
  if (!vcResourceChart) vcResourceChart = echarts.init(vcResourceRef.value)
  const items = stats.vcenter.per_vcenter
  const names = items.map(i => i.vcenter_name)
  const cpu = items.map(i => i.cpu_cores)
  const mem = items.map(i => i.memory_gb)

  vcResourceChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['CPU 核数', '内存 GB'], itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12, color: '#64748b' }, bottom: 0 },
    grid: { left: '3%', right: '4%', top: '3%', bottom: '12%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 11, color: '#64748b', width: 80, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    series: [
      { name: 'CPU 核数', type: 'bar', data: cpu, barWidth: 14, itemStyle: { color: '#6366f1', borderRadius: [0, 4, 4, 0] } },
      { name: '内存 GB', type: 'bar', data: mem, barWidth: 14, itemStyle: { color: '#06b6d4', borderRadius: [0, 4, 4, 0] } },
    ],
  }, { notMerge: true })
}

function renderQaxOS() {
  if (qaxOSEmpty.value || !qaxOSRef.value) return
  if (!qaxOSChart) qaxOSChart = echarts.init(qaxOSRef.value)
  const data = stats.qax.os_distribution
  qaxOSChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', top: '3%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: { type: 'category', data: data.map(d => d.label).reverse(), axisLabel: { fontSize: 10, color: '#64748b', width: 100, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, inverse: true },
    series: [{
      type: 'bar', data: data.map(d => d.count).reverse(),
      barWidth: 16,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#6366f1' }, { offset: 1, color: '#a78bfa' }
        ]),
        borderRadius: [0, 4, 4, 0],
      },
    }],
  }, { notMerge: true })
}

function renderVcOS() {
  if (vcOSEmpty.value || !vcOSRef.value) return
  if (!vcOSChart) vcOSChart = echarts.init(vcOSRef.value)
  const data = stats.vcenter.os_distribution
  vcOSChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', top: '3%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: { type: 'category', data: data.map(d => d.label).reverse(), axisLabel: { fontSize: 10, color: '#64748b', width: 110, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, inverse: true },
    series: [{
      type: 'bar', data: data.map(d => d.count).reverse(),
      barWidth: 16,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#06b6d4' }, { offset: 1, color: '#67e8f9' }
        ]),
        borderRadius: [0, 4, 4, 0],
      },
    }],
  }, { notMerge: true })
}

function renderVcCpu() {
  if (vcCpuEmpty.value || !vcCpuRef.value) return
  if (!vcCpuChart) vcCpuChart = echarts.init(vcCpuRef.value)
  const data = stats.vcenter.cpu_cores_distribution
  vcCpuChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', top: '8%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: data.map(d => d.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', name: '台', nameTextStyle: { fontSize: 10, color: '#94a3b8' }, axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [{
      type: 'bar', data: data.map(d => ({ value: d.count, itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#8b5cf6' }, { offset: 1, color: '#c4b5fd' }]), borderRadius: [6, 6, 0, 0] } })),
      barWidth: 36,
    }],
  }, { notMerge: true })
}

function renderVcMem() {
  if (vcMemEmpty.value || !vcMemRef.value) return
  if (!vcMemChart) vcMemChart = echarts.init(vcMemRef.value)
  const data = stats.vcenter.memory_distribution
  vcMemChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', top: '8%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: data.map(d => d.label), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, axisLabel: { color: '#64748b', fontSize: 11 } },
    yAxis: { type: 'value', name: '台', nameTextStyle: { fontSize: 10, color: '#94a3b8' }, axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    series: [{
      type: 'bar', data: data.map(d => ({ value: d.count, itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: '#f59e0b' }, { offset: 1, color: '#fcd34d' }]), borderRadius: [6, 6, 0, 0] } })),
      barWidth: 36,
    }],
  }, { notMerge: true })
}

function renderEsxiCpu() {
  if (esxiCpuEmpty.value || !esxiCpuRef.value) return
  if (!esxiCpuChart) esxiCpuChart = echarts.init(esxiCpuRef.value)
  const data = stats.vcenter.esxi_cpu_types
  esxiCpuChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '8%', top: '3%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: { type: 'category', data: data.map(d => d.label).reverse(), axisLabel: { fontSize: 10, color: '#64748b', width: 200, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } }, inverse: true },
    series: [{
      type: 'bar', data: data.map(d => d.count).reverse(),
      barWidth: 16,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#8b5cf6' }, { offset: 1, color: '#c4b5fd' }
        ]),
        borderRadius: [0, 4, 4, 0],
      },
    }],
  }, { notMerge: true })
}

function renderDsStorage() {
  if (dsStorageEmpty.value || !dsStorageRef.value) return
  if (!dsStorageChart) dsStorageChart = echarts.init(dsStorageRef.value)
  const data = stats.vcenter.datastore_by_type
  const names = data.map(d => `${d.storage_type} (${d.count}个)`)
  const capacity = data.map(d => d.capacity_gb)
  const free = data.map(d => d.free_gb)

  dsStorageChart.setOption({
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: function (params) {
        const el = data[params[0].dataIndex]
        const used = +(el.capacity_gb - el.free_gb).toFixed(1)
        return `<b>${el.storage_type}</b>（${el.count} 个）<br/>总容量: <b>${el.capacity_gb} GB</b><br/>已用: <b style="color:#f59e0b">${used} GB</b> | 可用: <b style="color:#10b981">${el.free_gb} GB</b>`
      }
    },
    legend: { data: ['总容量', '可用'], itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12, color: '#64748b' }, bottom: 0 },
    grid: { left: '3%', right: '4%', top: '3%', bottom: '12%', containLabel: true },
    xAxis: { type: 'value', name: 'GB', nameTextStyle: { color: '#94a3b8' }, axisLabel: { fontSize: 10, color: '#94a3b8' }, splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 11, color: '#64748b' }, axisTick: { show: false }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    series: [
      { name: '总容量', type: 'bar', data: capacity, barWidth: 14, itemStyle: { color: '#6366f1', borderRadius: [0, 4, 4, 0] } },
      { name: '可用', type: 'bar', data: free, barWidth: 14, itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] } },
    ],
  }, { notMerge: true })
}

function disposeCharts() {
  vmDonutChart?.dispose()
  dnsPieChart?.dispose()
  f5DonutChart?.dispose()
  scanBarChart?.dispose()
  subnetBarChart?.dispose()
  personalBarChart?.dispose()
  vcResourceChart?.dispose()
  qaxOSChart?.dispose()
  vcOSChart?.dispose()
  vcCpuChart?.dispose()
  vcMemChart?.dispose()
  esxiCpuChart?.dispose()
  dsStorageChart?.dispose()
}

onMounted(() => {
  if (authStore.isAdmin) { fetchStats(); fetchUtilization() }
  else { fetchPersonal() }
})

onBeforeUnmount(() => {
  disposeCharts()
})
</script>

<style scoped>
.dashboard h2 { margin: 0; font-size: 22px; font-weight: 700; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-desc { margin: 4px 0 0; font-size: 13px; color: var(--color-text-muted); }

/* ── 统计卡片 ── */
.stat-row { margin-bottom: 16px; }
.stat-card {
  cursor: pointer; transition: transform .2s, box-shadow .2s;
  display: flex; align-items: center; gap: 14px;
  background: var(--color-bg-card); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); padding: 16px 18px;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
.stat-icon {
  width: 46px; height: 46px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center; color: #fff; flex-shrink: 0;
}
.stat-info { text-align: left; min-width: 0; }
.stat-value { font-size: 26px; font-weight: 700; color: var(--color-text); line-height: 1.2; white-space: nowrap; }
.stat-sub { font-size: 11px; font-weight: 400; color: var(--color-text-muted); margin-left: 4px; }
.stat-title { font-size: 12px; color: var(--color-text-muted); margin-top: 2px; }

/* ── 图表通用 ── */
.chart-row { margin-bottom: 16px; }
.chart-card { height: 100%; }
.chart-box { height: 240px; }
.chart-box-wide { height: 320px; }
.chart-container { height: 350px; }
.stat-flex-row { display: flex; gap: 16px; }
.stat-flex-row > .stat-card { flex: 1; }
.empty-chart { display: flex; justify-content: center; padding: 16px 0; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-hint { font-size: 11px; color: var(--color-text-muted); font-weight: 400; }

/* ── 可用 IP ── */
.available-card { height: 100%; }
.ip-form { margin-bottom: 12px; }

/* ── 扫描摘要 ── */
.summary-card { height: 100%; }
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.summary-item { text-align: center; padding: 16px 8px; border-radius: var(--radius-sm); background: var(--color-bg); }
.summary-item.success .summary-num { color: #10b981; }
.summary-item.danger .summary-num { color: #ef4444; }
.summary-item.info .summary-num { color: #6366f1; }
.summary-item.primary .summary-num { color: #06b6d4; }
.summary-num { font-size: 28px; font-weight: 700; }
.summary-label { font-size: 12px; color: var(--color-text-muted); margin-top: 4px; }
.summary-source { border-top: 1px solid var(--color-border); padding-top: 12px; }
.source-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; color: var(--color-text-secondary); }
.source-count { font-weight: 600; color: var(--color-text); }

/* ── 对话框分页 ── */
.occupied-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }
.dialog-search-bar { margin-bottom: 16px; }

/* ── 资产卡片补充样式 ── */
.stat-detail { font-size: 11px; color: var(--color-text-muted); margin-top: 2px; }
.no-hover:hover { transform: none; box-shadow: none; }
</style>
