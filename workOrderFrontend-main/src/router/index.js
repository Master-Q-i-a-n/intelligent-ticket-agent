import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import DashboardView from '../views/DashboardView.vue'
import FeedbackView from '../views/FeedbackView.vue'
import ProfileView from '../views/ProfileView.vue'
import WorkOrderView from '../views/WorkOrderView.vue'
import { getDefaultRouteByRole, normalizeRole } from '../utils/auth'
import { hasSession, getSessionRole, restoreSession } from '../store/session'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/dashboard', component: DashboardView },
  { path: '/profile', component: ProfileView },
  { path: '/feedback', component: FeedbackView, meta: { roles: ['user'] } },
  { path: '/work-order', component: WorkOrderView, meta: { roles: ['admin'] } }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  restoreSession()
  if (to.path === '/login') {
    if (hasSession()) {
      next(getDefaultRouteByRole(getSessionRole()))
      return
    }
    next()
    return
  }

  if (!hasSession()) {
    next('/login')
    return
  }

  const allowedRoles = to.meta.roles || []
  const currentRole = normalizeRole(getSessionRole())
  if (allowedRoles.length > 0 && !allowedRoles.includes(currentRole)) {
    next(getDefaultRouteByRole(currentRole))
    return
  }

  next()
})

export default router
