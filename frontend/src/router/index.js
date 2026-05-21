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
        path: 'history',
        name: 'History',
        component: () => import('@/views/Placeholder.vue'),
        props: { title: '历史记录' },
        meta: { title: '历史记录' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Placeholder.vue'),
        props: { title: '用户管理' },
        meta: { title: '用户管理', admin: true },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Placeholder.vue'),
        props: { title: '个人设置' },
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
  } else {
    next()
  }
})

export default router
