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
        path: 'users',
        name: 'Users',
        component: () => import('@/views/UserManage.vue'),
        meta: { title: '用户管理', admin: true },
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
  if (to.meta.public) {
    next()
  } else if (!authStore.token) {
    next('/login')
  } else if (to.meta.admin && !authStore.isAdmin) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
