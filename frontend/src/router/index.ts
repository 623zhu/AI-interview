import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  // ==================== User Routes ====================
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/user/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    redirect: '/login',
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/home' },
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/user/HomeView.vue'),
      },
      { path: 'resume', redirect: '/home' },
      { path: 'interviews', redirect: '/home' },
      { path: 'dashboard', redirect: '/home' },
      {
        path: 'interview/:id',
        name: 'Interview',
        component: () => import('@/views/user/InterviewRoomView.vue'),
        meta: { title: '模拟面试' },
      },
      {
        path: 'report/:id',
        name: 'Report',
        component: () => import('@/views/user/ReportView.vue'),
        meta: { title: '面试报告' },
      },
    ],
  },

  // ==================== Admin Routes ====================
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      { path: '', redirect: '/admin/questions' },
      {
        path: 'dashboard',
        redirect: '/admin/analytics',
      },
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
        meta: { title: '创建岗位' },
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

  // 404
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Route guards
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // Allow guest routes
  if (to.meta.guest) {
    if (authStore.isLoggedIn && to.path === '/login') {
      return next(authStore.isAdmin ? '/admin/analytics' : '/home')
    }
    return next()
  }

  // Check auth
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    return next('/login')
  }

  // Check admin
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    return next('/resume')
  }

  next()
})

export default router
