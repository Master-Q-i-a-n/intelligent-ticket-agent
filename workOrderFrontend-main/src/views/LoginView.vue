<template>
  <section class="login-screen">
    <div class="login-panel">
      <div class="login-panel__copy">
        <p class="eyebrow">工单系统</p>
        <h1>登录后继续使用</h1>
        <p class="lead">
          系统可使用演示账号登录，也可以注册普通用户或管理员账号。
        </p>
      </div>

      <el-form class="login-form" :model="form" @submit.prevent>
        <el-form-item>
          <el-input v-model.trim="form.username" placeholder="用户名" />
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
        <div class="login-form__register">
          <el-button link type="primary" @click="openRegisterDialog">注册账号</el-button>
        </div>
      </el-form>
    </div>

    <el-dialog
      v-model="registerDialogVisible"
      title="注册账号"
      width="420px"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form class="register-form" :model="registerForm" label-position="top" @submit.prevent>
        <el-form-item label="用户名" required>
          <el-input v-model.trim="registerForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="显示名称" required>
          <el-input v-model.trim="registerForm.displayName" placeholder="请输入显示名称" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="registerForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="确认密码" required>
          <el-input v-model="registerForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password />
        </el-form-item>
        <el-form-item label="头像地址">
          <el-input v-model.trim="registerForm.avatarUrl" placeholder="可选" />
        </el-form-item>
        <el-form-item label="账号角色" required>
          <el-select v-model="registerForm.role" class="register-form__role">
            <el-option label="普通用户" value="USER" />
            <el-option label="管理员" value="ADMIN" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="registerForm.role === 'ADMIN'" label="客服组" required>
          <el-select v-model="registerForm.serviceGroup" class="register-form__role">
            <el-option v-for="item in TICKET_SERVICE_GROUP_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="registerDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="registerLoading" @click="submitRegister">
          注册并登录
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDemoAccount, login, register } from '../api/auth'
import { setSession } from '../store/session'
import { getDefaultRouteByRole } from '../utils/auth'
import { TICKET_SERVICE_GROUP_OPTIONS } from '../utils/ticket'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const demoLoading = ref(false)
const registerLoading = ref(false)
const registerDialogVisible = ref(false)
const form = reactive({
  username: '',
  password: ''
})
const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  displayName: '',
  avatarUrl: '',
  role: 'USER',
  serviceGroup: 'PRODUCT_CONSULTING'
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

function openRegisterDialog() {
  registerDialogVisible.value = true
}

function validateRegisterForm() {
  if (!registerForm.username || !registerForm.displayName || !registerForm.password || !registerForm.confirmPassword) {
    ElMessage.warning('请填写完整注册信息')
    return false
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    ElMessage.warning('两次输入的密码不一致')
    return false
  }
  if (!['USER', 'ADMIN'].includes(registerForm.role)) {
    ElMessage.warning('请选择账号角色')
    return false
  }
  if (registerForm.role === 'ADMIN' && !TICKET_SERVICE_GROUP_OPTIONS.some(item => item.value === registerForm.serviceGroup)) {
    ElMessage.warning('请选择客服组')
    return false
  }
  return true
}

async function submitRegister() {
  if (!validateRegisterForm()) {
    return
  }

  registerLoading.value = true
  try {
    const res = await register({
      username: registerForm.username,
      password: registerForm.password,
      displayName: registerForm.displayName,
      avatarUrl: registerForm.avatarUrl,
      role: registerForm.role,
      serviceGroup: registerForm.role === 'ADMIN' ? registerForm.serviceGroup : undefined
    })
    setSession(res.data)
    ElMessage.success('注册成功')
    registerDialogVisible.value = false
    await router.replace(getDefaultRouteByRole(res.data.user.role))
  } catch (error) {
    ElMessage.error(error.message || '注册失败')
  } finally {
    registerLoading.value = false
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
