<template>
  <section class="profile-page">
    <div class="profile-page__hero">
      <div>
        <p class="eyebrow">个人中心</p>
        <h2>管理你的账户信息</h2>
        <p class="lead">
          这里可以修改昵称、上传头像到服务器，并更新登录密码。账号名只读展示，方便你确认当前登录身份。
        </p>
      </div>
      <div class="profile-page__identity">
        <el-avatar class="profile-page__avatar" :size="96" :src="avatarPreview">
          {{ avatarFallback }}
        </el-avatar>
        <div>
          <div class="profile-page__account">{{ form.username }}</div>
          <div class="profile-page__hint">{{ form.displayName || '未设置昵称' }}</div>
        </div>
      </div>
    </div>

    <div class="profile-grid">
      <section class="panel profile-card">
        <div class="profile-card__header">
          <div>
            <p class="page-header__eyebrow">基础资料</p>
            <h3>昵称和头像</h3>
          </div>
          <el-button :loading="profileSaving" type="primary" @click="saveProfile">保存资料</el-button>
        </div>

        <el-form class="profile-form" :model="form" label-position="top">
          <el-form-item label="账号名">
            <el-input :model-value="form.username" disabled />
          </el-form-item>

          <el-form-item label="昵称">
            <el-input v-model="form.displayName" placeholder="请输入昵称" />
          </el-form-item>

          <el-form-item label="头像">
            <div class="profile-avatar-upload">
              <el-avatar class="profile-avatar-upload__preview" :size="72" :src="avatarPreview">
                {{ avatarFallback }}
              </el-avatar>
              <div class="profile-avatar-upload__actions">
                <input
                  ref="avatarInputRef"
                  class="profile-avatar-upload__input"
                  type="file"
                  accept="image/*"
                  @change="handleAvatarChange"
                >
                <el-button :loading="avatarUploading" @click="triggerAvatarInput">上传头像</el-button>
                <div class="profile-card__meta">
                  图片先上传到服务器，再把返回地址写回个人资料。
                </div>
              </div>
            </div>
          </el-form-item>
        </el-form>
      </section>

      <section class="panel profile-card">
        <div class="profile-card__header">
          <div>
            <p class="page-header__eyebrow">安全设置</p>
            <h3>修改密码</h3>
          </div>
          <el-button :loading="passwordSaving" type="primary" plain @click="savePassword">更新密码</el-button>
        </div>

        <el-form class="profile-form" :model="passwordForm" label-position="top">
          <el-form-item label="当前密码">
            <el-input v-model="passwordForm.oldPassword" type="password" show-password placeholder="请输入当前密码" />
          </el-form-item>

          <el-form-item label="新密码">
            <el-input v-model="passwordForm.newPassword" type="password" show-password placeholder="请输入新密码" />
          </el-form-item>

          <el-form-item label="确认新密码">
            <el-input v-model="passwordForm.confirmPassword" type="password" show-password placeholder="再次输入新密码" />
          </el-form-item>
        </el-form>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getCurrentUser, updatePassword, updateProfile } from '../api/auth'
import { uploadFile } from '../api/file'
import { sessionState, updateSessionUser } from '../store/session'

const profileSaving = ref(false)
const passwordSaving = ref(false)
const avatarUploading = ref(false)
const avatarInputRef = ref(null)

const form = reactive({
  username: '',
  displayName: '',
  avatarUrl: ''
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const avatarPreview = computed(() => form.avatarUrl || '')
const avatarFallback = computed(() => (form.displayName || form.username || 'U').slice(0, 1).toUpperCase())

function fillFromUser(user) {
  form.username = user?.username || ''
  form.displayName = user?.displayName || ''
  form.avatarUrl = user?.avatarUrl || ''
}

async function loadProfile() {
  const res = await getCurrentUser()
  fillFromUser(res.data)
  updateSessionUser(res.data)
}

function triggerAvatarInput() {
  avatarInputRef.value?.click()
}

async function handleAvatarChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) {
    return
  }

  avatarUploading.value = true
  try {
    const res = await uploadFile(file, 'avatar')
    const uploaded = res.data?.url || res.data?.fileUrl || res.data?.imgUrl || ''
    if (!uploaded) {
      throw new Error('上传失败，请重试')
    }
    form.avatarUrl = uploaded
    ElMessage.success('头像已上传')
  } catch (error) {
    ElMessage.error(error.message || '头像上传失败')
  } finally {
    avatarUploading.value = false
  }
}

async function saveProfile() {
  if (!form.displayName.trim()) {
    ElMessage.warning('请输入昵称')
    return
  }

  profileSaving.value = true
  try {
    const res = await updateProfile({
      displayName: form.displayName.trim(),
      avatarUrl: form.avatarUrl
    })
    updateSessionUser(res.data)
    fillFromUser(res.data)
    ElMessage.success('资料已保存')
  } catch (error) {
    ElMessage.error(error.message || '保存资料失败')
  } finally {
    profileSaving.value = false
  }
}

async function savePassword() {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    ElMessage.warning('请输入当前密码和新密码')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }

  passwordSaving.value = true
  try {
    await updatePassword({
      oldPassword: passwordForm.oldPassword,
      newPassword: passwordForm.newPassword
    })
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
    ElMessage.success('密码已更新')
  } catch (error) {
    ElMessage.error(error.message || '更新密码失败')
  } finally {
    passwordSaving.value = false
  }
}

onMounted(() => {
  if (sessionState.user) {
    fillFromUser(sessionState.user)
  }
  loadProfile().catch(() => {
    fillFromUser(sessionState.user)
  })
})
</script>
