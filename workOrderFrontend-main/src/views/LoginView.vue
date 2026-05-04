<template>
  <section class="login-screen">
    <div class="login-panel">
      <div class="login-panel__copy">
        <p class="eyebrow">工单系统</p>
        <h1>登录后继续使用</h1>
        <p class="lead">
          系统仅作演示，点击按钮可直接填入默认账号密码。
        </p>
      </div>

      <el-form class="login-form" :model="form" @submit.prevent>
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" class="login-form__submit" :loading="loading" @click="submit">
          登录
        </el-button>
        <div class="login-form__quick">
          <el-button text :loading="demoLoading" @click="fillUser">填入用户账号</el-button>
          <el-button text :loading="demoLoading" @click="fillAdmin">填入管理员账号</el-button>
        </div>
      </el-form>
    </div>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDemoAccount, login } from '../api/auth'
import { setSession } from '../store/session'
import { getDefaultRouteByRole } from '../utils/auth'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const demoLoading = ref(false)
const form = reactive({
  username: '',
  password: ''
})

async function fillUser() {
  await fillDemoAccount('user')
}

async function fillAdmin() {
  await fillDemoAccount('admin')
}

async function fillDemoAccount(username) {
  demoLoading.value = true
  try {
    const res = await getDemoAccount(username)
    Object.assign(form, res.data)
  } catch (error) {
    ElMessage.error(error.message || '获取演示账号失败')
  } finally {
    demoLoading.value = false
  }
}

async function submit() {
  loading.value = true
  try {
    const res = await login(form)
    setSession(res.data)
    ElMessage.success('登录成功')
    await router.replace(getDefaultRouteByRole(res.data.user.role))
  } catch (error) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
