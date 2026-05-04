<template>
  <RouterView v-if="isLoginRoute" />
  <div v-else class="app-shell">
    <aside class="app-shell__sidebar">
      <div class="brand">
        <div class="brand__mark">WO</div>
        <div>
          <div class="brand__name">工单系统</div>
          <div class="brand__sub">{{ roleLabel }}</div>
          <div class="brand__user" v-if="sessionState.user">{{ sessionState.user.displayName || sessionState.user.username }}</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink class="nav__item" to="/dashboard">首页</RouterLink>
        <RouterLink class="nav__item" to="/feedback" v-if="isUser">我的反馈</RouterLink>
        <RouterLink class="nav__item" to="/work-order" v-if="isAdmin">工单管理</RouterLink>
      </nav>
    </aside>

    <main class="app-shell__main">
      <header class="app-shell__topbar">
        <div>
          <p class="app-shell__eyebrow">{{ sectionLabel }}</p>
          <h1 class="app-shell__title">{{ sectionTitle }}</h1>
        </div>

        <el-dropdown trigger="click" @command="handleMenuCommand">
          <button class="user-chip" type="button">
            <el-avatar class="user-chip__avatar" :size="36" :src="avatarUrl">
              {{ avatarFallback }}
            </el-avatar>
            <span class="user-chip__meta">
              <span class="user-chip__name">{{ displayName }}</span>
              <span class="user-chip__account">{{ accountName }}</span>
            </span>
            <span class="user-chip__arrow">▾</span>
          </button>

          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>

      <section class="app-shell__content">
        <RouterView />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { removeSession, sessionState } from './store/session'
import { normalizeRole } from './utils/auth'
import { logout } from './api/auth'

const route = useRoute()
const router = useRouter()

const isLoginRoute = computed(() => route.path === '/login')
const role = computed(() => normalizeRole(sessionState.user?.role))
const isUser = computed(() => role.value === 'user')
const isAdmin = computed(() => role.value === 'admin')
const roleLabel = computed(() => ({
  user: '用户端',
  admin: '管理端',
  guest: '游客'
}[role.value] || '游客'))

const sectionTitleMap = {
  '/dashboard': '概览',
  '/feedback': '我的反馈',
  '/work-order': '工单管理',
  '/profile': '个人中心'
}

const sectionLabelMap = {
  '/dashboard': '主页',
  '/feedback': '用户侧',
  '/work-order': '管理侧',
  '/profile': '账户设置'
}

const sectionTitle = computed(() => sectionTitleMap[route.path] || '工单系统')
const sectionLabel = computed(() => sectionLabelMap[route.path] || '工作台')
const displayName = computed(() => sessionState.user?.displayName || sessionState.user?.username || '用户')
const accountName = computed(() => `账号：${sessionState.user?.username || '-'}`)
const avatarUrl = computed(() => sessionState.user?.avatarUrl || '')
const avatarFallback = computed(() => (displayName.value || 'U').slice(0, 1).toUpperCase())

async function handleMenuCommand(command) {
  if (command === 'profile') {
    await router.push('/profile')
    return
  }

  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch (error) {
      return
    }

    try {
      await logout()
    } catch (error) {
      // ignore backend logout failures for local sign-out
    }
    removeSession()
    ElMessage.success('已退出登录')
    await router.replace('/login')
  }
}
</script>
