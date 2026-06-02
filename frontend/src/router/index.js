import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '仪表盘' },
      },
      {
        path: 'switches',
        name: 'Switches',
        component: () => import('@/views/SwitchList.vue'),
        meta: { title: '交换机管理' },
      },
      {
        path: 'switches/:id',
        name: 'SwitchDetail',
        component: () => import('@/views/SwitchDetail.vue'),
        meta: { title: '交换机详情' },
      },
      {
        path: 'vcenters',
        name: 'VCenters',
        component: () => import('@/views/VCenterList.vue'),
        meta: { title: 'vCenter 管理' },
      },
      {
        path: 'vcenters/:id',
        name: 'VCenterDetail',
        component: () => import('@/views/VCenterDetail.vue'),
        meta: { title: 'vCenter 详情' },
      },
      {
        path: 'f5',
        name: 'F5Devices',
        component: () => import('@/views/F5List.vue'),
        meta: { title: 'F5 管理' },
      },
      {
        path: 'f5/:id',
        name: 'F5Detail',
        component: () => import('@/views/F5Detail.vue'),
        meta: { title: 'F5 详情' },
      },
      {
        path: 'zdns',
        name: 'ZDNSDevices',
        component: () => import('@/views/ZDNSList.vue'),
        meta: { title: 'ZDNS 管理' },
      },
      {
        path: 'zdns/:id',
        name: 'ZDNSDetail',
        component: () => import('@/views/ZDNSDetail.vue'),
        meta: { title: 'ZDNS 详情' },
      },
      {
        path: 'qax',
        name: 'QAXDevices',
        component: () => import('@/views/QAXList.vue'),
        meta: { title: '椒图管理' },
      },
      {
        path: 'qax/:id',
        name: 'QAXDetail',
        component: () => import('@/views/QAXDetail.vue'),
        meta: { title: '椒图详情' },
      },
      {
        path: 'results',
        name: 'Results',
        component: () => import('@/views/Results.vue'),
        meta: { title: '扫描结果' },
      },
      {
        path: 'routes',
        name: 'Routes',
        component: () => import('@/views/Routes.vue'),
        meta: { title: '路由表' },
      },
      {
        path: 'subnets',
        name: 'Subnets',
        component: () => import('@/views/SubnetManage.vue'),
        meta: { title: '地址段管理' },
      },
      {
        path: 'search',
        name: 'Search',
        component: () => import('@/views/SearchResult.vue'),
        meta: { title: '搜索' },
      },
      {
        path: 'scan-monitor',
        name: 'ScanMonitor',
        component: () => import('@/views/ScanMonitor.vue'),
        meta: { title: '扫描监控' },
      },
      {
        path: 'scan-logs',
        name: 'ScanLogs',
        component: () => import('@/views/ScanLogs.vue'),
        meta: { title: '扫描日志' },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/History.vue'),
        meta: { title: '历史记录' },
      },
      {
        path: 'sys/api-config',
        name: 'ApiConfig',
        component: () => import('@/views/system/ApiConfig.vue'),
        meta: { title: 'API 配置', admin: true },
      },
      {
        path: 'sys/assets',
        name: 'AssetManage',
        component: () => import('@/views/assets/AssetManage.vue'),
        meta: { title: '信息资产管理' },
      },
      {
        path: 'sys/departments',
        name: 'OrgManage',
        component: () => import('@/views/system/OrgManage.vue'),
        meta: { title: '组织机构管理', admin: true },
      },
      {
        path: 'sys/accounts',
        name: 'AccountManage',
        component: () => import('@/views/system/AccountManage.vue'),
        meta: { title: '账号管理', admin: true },
      },
      {
        path: 'sys/workers',
        name: 'Workers',
        component: () => import('@/views/WorkerManage.vue'),
        meta: { title: 'Worker 管理', admin: true },
      },
      {
        path: 'sys/scheduler',
        name: 'SchedulerMonitor',
        component: () => import('@/views/system/SchedulerMonitor.vue'),
        meta: { title: '定时任务', admin: true },
      },
      {
        path: 'asset-profile',
        name: 'AssetProfile',
        component: () => import('@/views/AssetProfile.vue'),
        meta: { title: '资产画像' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人设置' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  // CAS 回调：从 URL 中提取 token
  const casToken = to.query.cas_token
  if (casToken && typeof casToken === 'string') {
    localStorage.setItem('token', casToken)
    authStore.token = casToken
    // 获取用户信息后跳转
    authStore.fetchUser().finally(() => {
      const cleanQuery = { ...to.query }
      delete cleanQuery.cas_token
      next({ path: '/dashboard', query: cleanQuery, replace: true })
    })
    return
  }

  if (to.meta.public) {
    next()
  } else if (!authStore.token) {
    // 访问系统时直接跳转 CAS 认证，/login 页面手动登录
    window.location.href = '/api/auth/cas/login'
    return
  } else if (to.meta.admin && !authStore.isAdmin) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
