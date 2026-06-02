<template>
  <el-container class="layout">
    <el-aside :width="isCollapse ? '64px' : '232px'" class="sidebar">
      <div class="logo">
        <div class="logo-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="6" fill="url(#logo-grad)"/>
            <text x="12" y="17" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">OV</text>
            <defs>
              <linearGradient id="logo-grad" x1="0" y1="0" x2="24" y2="24">
                <stop stop-color="#6366f1"/>
                <stop offset="1" stop-color="#8b5cf6"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <span v-show="!isCollapse" class="logo-text">OmniView</span>
        <span v-show="isCollapse" class="logo-text-collapsed">OV</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        router
        background-color="transparent"
        text-color="var(--sidebar-text)"
        active-text-color="var(--sidebar-text-active)"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/asset-profile">
          <el-icon><DataAnalysis /></el-icon>
          <span>资产画像</span>
        </el-menu-item>
        <el-sub-menu index="/sys/info">
          <template #title>
            <el-icon><DataBoard /></el-icon>
            <span>信息资产管理</span>
          </template>
          <el-menu-item index="/sys/assets">信息资产总览</el-menu-item>
          <el-menu-item index="/sys/info-systems">信息系统维护</el-menu-item>
          <el-menu-item index="/sys/djdj">等保信息维护</el-menu-item>
          <el-menu-item index="/sys/icp">ICP备案维护</el-menu-item>
        </el-sub-menu>

        <div class="menu-group-title" v-show="!isCollapse">资产管理</div>
        <el-menu-item index="/dingjia">
          <el-icon><FolderOpened /></el-icon>
          <span>鼎甲备份管理</span>
        </el-menu-item>
        <el-menu-item index="/switches">
          <el-icon><Monitor /></el-icon>
          <span>交换机管理</span>
        </el-menu-item>
        <el-menu-item index="/vcenters">
          <el-icon><Cloudy /></el-icon>
          <span>vCenter 管理</span>
        </el-menu-item>
        <el-menu-item index="/f5">
          <el-icon><Connection /></el-icon>
          <span>F5 管理</span>
        </el-menu-item>
        <el-menu-item index="/zdns">
          <el-icon><Link /></el-icon>
          <span>ZDNS 管理</span>
        </el-menu-item>
        <el-menu-item index="/qax">
          <el-icon><Monitor /></el-icon>
          <span>椒图管理</span>
        </el-menu-item>

        <div class="menu-group-title" v-show="!isCollapse">扫描分析</div>
        <el-menu-item index="/results">
          <el-icon><List /></el-icon>
          <span>扫描结果</span>
        </el-menu-item>
        <el-menu-item index="/routes">
          <el-icon><Connection /></el-icon>
          <span>路由表</span>
        </el-menu-item>
        <el-menu-item index="/subnets">
          <el-icon><Grid /></el-icon>
          <span>地址段管理</span>
        </el-menu-item>
        <el-menu-item index="/scan-monitor">
          <el-icon><TrendCharts /></el-icon>
          <span>扫描监控</span>
        </el-menu-item>
        <el-menu-item index="/scan-logs">
          <el-icon><Tickets /></el-icon>
          <span>扫描日志</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Clock /></el-icon>
          <span>历史记录</span>
        </el-menu-item>

        <template v-if="authStore.isAdmin">
          <div class="menu-group-title" v-show="!isCollapse">系统管理</div>
          <el-sub-menu index="/sys">
            <template #title>
              <el-icon><Setting /></el-icon>
              <span>系统管理</span>
            </template>
            <el-menu-item index="/sys/api-config">
              <el-icon><Coin /></el-icon>
              <span>API 配置</span>
            </el-menu-item>
            <el-menu-item index="/sys/departments">
              <el-icon><OfficeBuilding /></el-icon>
              <span>组织机构管理</span>
            </el-menu-item>
            <el-menu-item index="/sys/accounts">
              <el-icon><UserFilled /></el-icon>
              <span>账号管理</span>
            </el-menu-item>
            <el-menu-item index="/sys/workers">
              <el-icon><Cpu /></el-icon>
              <span>Worker 管理</span>
            </el-menu-item>
            <el-menu-item index="/sys/scheduler">
              <el-icon><Timer /></el-icon>
              <span>定时任务</span>
            </el-menu-item>
          </el-sub-menu>
        </template>
      </el-menu>

      <div class="sidebar-footer" v-show="!isCollapse">
        <div class="version">OmniView v{{ appVersion }}</div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="navbar">
        <div class="navbar-left">
          <el-button text class="collapse-btn" @click="isCollapse = !isCollapse">
            <el-icon :size="18">
              <Fold v-if="!isCollapse" /><Expand v-else />
            </el-icon>
          </el-button>
          <el-breadcrumb separator="">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">
              <el-icon><HomeFilled /></el-icon>
            </el-breadcrumb-item>
            <span class="breadcrumb-sep" v-if="pageTitle">/</span>
            <el-breadcrumb-item v-if="pageTitle">{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="navbar-right">
          <el-input
            v-model="searchText"
            placeholder="搜索 IP 或 MAC 地址..."
            class="search-input"
            clearable
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-dropdown trigger="click">
            <span class="user-info">
              <el-avatar :size="34" class="user-avatar">
                {{ authStore.user?.username?.charAt(0)?.toUpperCase() }}
              </el-avatar>
              <span class="username">{{ authStore.user?.username }}</span>
              <el-icon class="arrow-icon"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="$router.push('/profile')">
                  <el-icon><Setting /></el-icon>个人设置
                </el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'
import { getVersion } from '@/api/version'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isCollapse = ref(false)
const searchText = ref('')
const appVersion = ref('1.0.0')

const activeMenu = computed(() => {
  if (route.path.startsWith('/sys/')) return route.path
  return '/' + route.path.split('/')[1]
})

const pageTitle = computed(() => {
  const titles = {
    '/dashboard': '仪表盘',
    '/switches': '交换机管理',
    '/vcenters': 'vCenter 管理',
    '/f5': 'F5 管理',
    '/zdns': 'ZDNS 管理',
    '/qax': '椒图管理',
    '/results': '扫描结果',
    '/routes': '路由表',
    '/subnets': '地址段管理',
    '/scan-monitor': '扫描监控',
    '/scan-logs': '扫描日志',
    '/history': '历史记录',
    '/asset-profile': '资产画像',
    '/profile': '个人设置',
    '/search': '搜索结果',
    '/dingjia': '鼎甲备份管理',
    '/sys/api-config': 'API 配置',
    '/sys/assets': '信息资产管理',
    '/sys/info-systems': '信息系统维护',
    '/sys/djdj': '等保信息维护',
    '/sys/icp': 'ICP备案维护',
    '/sys/departments': '组织机构管理',
    '/sys/accounts': '账号管理',
    '/sys/workers': 'Worker 管理',
    '/sys/scheduler': '定时任务',
  }
  return titles[route.path] || ''
})

function handleSearch() {
  const q = searchText.value.trim()
  if (q) {
    router.push({ path: '/search', query: { q } })
  }
}

function handleLogout() {
  authStore.logout()
  window.location.href = '/api/auth/cas/logout'
}

onMounted(async () => {
  try {
    const data = await getVersion()
    appVersion.value = data.version
  } catch { /* */ }
})
</script>

<style scoped>
.layout {
  height: 100vh;
}

/* ═══════════════ 侧边栏 ═══════════════ */
.sidebar {
  background: var(--sidebar-bg);
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding: 0 16px;
}

.logo-icon {
  flex-shrink: 0;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 2px;
}

.logo-text-collapsed {
  font-size: 14px;
  font-weight: 700;
  color: #fff;
}

.menu-group-title {
  padding: 12px 20px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: rgba(255, 255, 255, 0.25);
  user-select: none;
}

.sidebar-footer {
  margin-top: auto;
  padding: 16px;
  text-align: center;
}

.version {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.25);
  letter-spacing: 0.5px;
}

/* ═══════════════ 顶栏 ═══════════════ */
.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  padding: 0 24px;
  height: 56px;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.collapse-btn {
  color: var(--color-text-secondary);
  padding: 6px;
}

.breadcrumb-sep {
  color: var(--color-text-muted);
  margin: 0 4px;
  font-size: 13px;
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.search-input {
  width: 300px;
}

.search-input :deep(.el-input__wrapper) {
  background: var(--color-bg);
  border-radius: 8px;
  padding: 1px 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.user-info:hover {
  background: var(--color-bg);
}

.user-avatar {
  background: linear-gradient(135deg, var(--color-primary), #8b5cf6);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
}

.username {
  font-size: 14px;
  color: var(--color-text);
  font-weight: 500;
}

.arrow-icon {
  font-size: 12px;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
}

/* ═══════════════ 主内容区 ═══════════════ */
.main-content {
  background: var(--color-bg);
  padding: 24px;
  min-height: 0;
  overflow-y: auto;
}
</style>
