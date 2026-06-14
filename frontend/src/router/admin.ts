import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/admin/AdminLoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      { path: '', redirect: '/admin/questions' },
      { path: 'dashboard', redirect: '/admin/analytics' },
      {
        path: 'questions',
        name: 'QuestionManage',
        component: () => import('@/views/admin/QuestionManageView.vue'),
        meta: { title: '题库管理' },
      },
      {
        path: 'questions/import',
        name: 'QuestionImport',
        component: () => import('@/views/admin/QuestionImportView.vue'),
        meta: { title: '导入题目' },
      },
      {
        path: 'questions/create',
        name: 'QuestionCreate',
        component: () => import('@/views/admin/QuestionEditView.vue'),
        meta: { title: '新增题目' },
      },
      {
        path: 'questions/:id',
        name: 'QuestionEdit',
        component: () => import('@/views/admin/QuestionEditView.vue'),
        meta: { title: '编辑题目' },
      },
      {
        path: 'jobs',
        name: 'JobManage',
        component: () => import('@/views/admin/JobManageView.vue'),
        meta: { title: '岗位管理' },
      },
      {
        path: 'jobs/create',
        name: 'JobCreate',
        component: () => import('@/views/admin/JobEditView.vue'),
        meta: { title: '新增岗位' },
      },
      {
        path: 'jobs/:id/edit',
        name: 'JobEdit',
        component: () => import('@/views/admin/JobEditView.vue'),
        meta: { title: '编辑岗位' },
      },
      {
        path: 'users',
        name: 'UserManage',
        component: () => import('@/views/admin/UserManageView.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'analytics',
        name: 'Analytics',
        component: () => import('@/views/admin/AnalyticsView.vue'),
        meta: { title: '数据统计' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/admin' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.guest) {
    if (authStore.isLoggedIn && to.path === '/login') {
      return next('/admin/analytics')
    }
    return next()
  }

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    return next('/login')
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return next('/login')
  }

  next()
})

export default router
