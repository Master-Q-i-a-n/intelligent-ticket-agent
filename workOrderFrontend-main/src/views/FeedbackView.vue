<template>
  <section class="feedback-page" v-loading="loading">
    <div class="feedback-page__header">
      <div>
        <p class="feedback-page__eyebrow">我的反馈</p>
        <h2 class="feedback-page__title">提交并查看反馈</h2>
      </div>
      <el-button type="primary" class="feedback-page__create" @click="openCreateDialog">
        <el-icon class="feedback-page__create-icon"><Plus /></el-icon>
        新建反馈
      </el-button>
    </div>

    <div class="feedback-toolbar">
      <el-input
        v-model.trim="searchInput"
        clearable
        placeholder="搜索反馈编号、标题、描述或账号名称"
        class="feedback-toolbar__search"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="statusFilter"
        clearable
        placeholder="全部状态"
        class="feedback-toolbar__status"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-button type="primary" class="feedback-toolbar__action" @click="handleSearch">查询</el-button>
    </div>

    <div v-if="!feedbackList.length && !searchInput && !loading" class="feedback-empty feedback-empty--page">
      <p class="feedback-empty__text">
        还没有反馈记录。点击“新建反馈”提交问题后，客服处理进度和回复会在这里同步显示。
      </p>
    </div>

    <div v-else-if="!feedbackList.length && searchInput && !loading" class="feedback-empty feedback-empty--page">
      <p class="feedback-empty__text">没有找到匹配的反馈记录，请尝试调整关键字或状态筛选。</p>
    </div>

    <div v-else class="feedback-layout">
      <div class="feedback-list">
        <el-scrollbar height="640px">
          <button
            v-for="item in feedbackList"
            :key="item.id"
            type="button"
            class="feedback-card"
            :class="{ 'is-active': selectedFeedback && selectedFeedback.id === item.id }"
            @click="handleSelectFeedback(item.id)"
          >
            <div class="feedback-card__code">{{ item.code }}</div>
            <div class="feedback-card__title">{{ item.title }}</div>
            <div class="feedback-card__desc">{{ item.description }}</div>
            <div class="feedback-card__footer">
              <span class="feedback-status" :class="toStatusMeta(item.status).className">
                <el-icon><component :is="statusIcon(item.status)" /></el-icon>
                {{ toStatusMeta(item.status).label }}
              </span>
              <span class="feedback-card__count">
                <el-icon><ChatDotRound /></el-icon>
                {{ item.replies.length }}
              </span>
            </div>
            <div class="feedback-card__time">更新于{{ formatTicketTime(item.updatedAt) }}</div>
          </button>
        </el-scrollbar>
      </div>

      <div class="feedback-detail" v-loading="detailLoading">
        <template v-if="selectedFeedback">
          <div class="feedback-detail__header">
            <div class="feedback-detail__code-row">
              <span class="feedback-detail__code">{{ selectedFeedback.code }}</span>
              <span class="feedback-status" :class="toStatusMeta(selectedFeedback.status).className">
                <el-icon><component :is="statusIcon(selectedFeedback.status)" /></el-icon>
                {{ toStatusMeta(selectedFeedback.status).label }}
              </span>
            </div>
            <h3 class="feedback-detail__title">{{ selectedFeedback.title }}</h3>
            <div class="feedback-detail__desc" :class="{ 'is-expanded': detailExpanded }">
              {{ selectedFeedback.description }}
            </div>
            <button
              v-if="shouldShowDetailToggle"
              type="button"
              class="feedback-detail__toggle"
              :class="{ 'is-expanded': detailExpanded }"
              @click="detailExpanded = !detailExpanded"
            >
              {{ detailExpanded ? '收起' : '更多' }}
              <el-icon>
                <component :is="detailExpanded ? ArrowUp : ArrowDown" />
              </el-icon>
            </button>

            <div v-if="selectedFeedback.images.length || selectedFeedback.attachments.length" class="feedback-assets">
              <div v-if="selectedFeedback.images.length" class="feedback-assets__block">
                <span class="feedback-assets__label">问题图片</span>
                <div class="feedback-assets__images">
                  <button
                    v-for="image in selectedFeedback.images"
                    :key="image.uid"
                    type="button"
                    class="feedback-assets__image"
                    @click="previewAsset(image)"
                  >
                    <img :src="getAssetPreviewUrl(image)" :alt="image.name" />
                  </button>
                </div>
              </div>

              <div v-if="selectedFeedback.attachments.length" class="feedback-assets__block">
                <span class="feedback-assets__label">问题附件</span>
                <div class="feedback-assets__files">
                  <button
                    v-for="file in selectedFeedback.attachments"
                    :key="file.uid"
                    type="button"
                    class="feedback-file"
                    @click="previewAsset(file)"
                  >
                    <el-icon><Paperclip /></el-icon>
                    {{ file.name }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="feedback-replies">
            <div class="feedback-replies__title">回复记录</div>
            <div ref="replyHistory" class="feedback-replies__list">
              <div
                v-for="reply in selectedFeedback.replies"
                :key="reply.id"
                class="feedback-reply"
                :class="{ 'is-service': reply.role === 'service' }"
              >
                <div class="feedback-reply__meta">
                  <div class="feedback-reply__author">
                    <span>{{ reply.author }}</span>
                    <span class="feedback-reply__tag" :class="{ 'is-user': reply.role !== 'service' }">{{ reply.roleLabel }}</span>
                  </div>
                  <span>{{ formatTicketTime(reply.createdAt) }}</span>
                </div>
                <div
                  class="feedback-reply__content feedback-rich-text"
                  v-html="renderReplyContent(reply.content)"
                  @click="handleRichTextClick"
                ></div>
                </div>
              </div>
            </div>

          <div v-if="canReplySelected" class="feedback-composer">
            <cs-reply-quill
              ref="replyEditor"
              v-model="replyForm.content"
              class="feedback-composer__editor"
              placeholder="请输入你的回复..."
              :max-length="500"
              @state-change="handleReplyEditorState"
            />

            <div class="feedback-composer__actions">
              <div class="feedback-composer__tools">
                <span class="feedback-composer__tip">正文内容 {{ replyTextLength }}/500 字</span>
              </div>
              <el-button type="primary" class="feedback-composer__submit" :loading="replyLoading" @click="submitReply">
                发送回复
              </el-button>
            </div>
          </div>

          <div v-else class="feedback-locked">
            当前反馈状态为“{{ toStatusMeta(selectedFeedback.status).label }}”，已关闭回复入口。
          </div>
        </template>

        <template v-else>
          <div class="feedback-empty feedback-empty--detail">
            <p class="feedback-empty__text">请从左侧选择一条反馈记录查看详情。</p>
          </div>
        </template>
      </div>
    </div>

    <el-dialog
      v-model="createDialogVisible"
      title="新建反馈"
      width="720px"
      append-to-body
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <div class="feedback-dialog">
        <div class="feedback-dialog__section-title">我遇到的问题</div>

        <div class="feedback-form-item">
          <label class="feedback-form-item__label is-required">问题标题</label>
          <el-input v-model.trim="createForm.title" maxlength="50" show-word-limit placeholder="请输入问题标题" />
        </div>

        <div class="feedback-form-item">
          <label class="feedback-form-item__label is-required">问题描述</label>
          <el-input
            v-model.trim="createForm.description"
            type="textarea"
            :rows="6"
            maxlength="500"
            show-word-limit
            resize="none"
            placeholder="请尽量描述清楚问题现象、影响范围和复现步骤"
          />
        </div>

        <div class="feedback-form-item">
          <label class="feedback-form-item__label">问题图片（{{ createForm.images.length }}/5）</label>
          <div class="feedback-attachment-toolbar">
            <button
              type="button"
              class="feedback-tool"
              :disabled="uploadingImages || createForm.images.length >= 5"
              @click="openImagePicker"
            >
              <el-icon><UploadFilled /></el-icon>
              {{ uploadingImages ? '上传中...' : '添加图片' }}
            </button>
            <span class="feedback-tool__hint">支持 jpg、png、gif、webp</span>
          </div>
          <div v-if="createForm.images.length" class="feedback-assets__files feedback-assets__files--wrap">
            <span v-for="(image, index) in createForm.images" :key="image.uid" class="feedback-file feedback-file--editable">
              <button type="button" class="feedback-file__link" @click="previewAsset(image)">
                <el-icon><Picture /></el-icon>
                {{ image.name }}
              </button>
              <button type="button" class="feedback-file__remove" @click="removeCreateImage(index)">删除</button>
            </span>
          </div>
        </div>

        <div class="feedback-form-item">
          <label class="feedback-form-item__label">问题附件</label>
          <div class="feedback-attachment-toolbar">
            <button type="button" class="feedback-tool" :disabled="uploadingAttachments" @click="openAttachmentPicker">
              <el-icon><Paperclip /></el-icon>
              {{ uploadingAttachments ? '上传中...' : '添加附件' }}
            </button>
            <span class="feedback-tool__hint">支持 pdf、xls、xlsx、doc、docx</span>
          </div>
          <div v-if="createForm.attachments.length" class="feedback-assets__files">
            <span v-for="(file, index) in createForm.attachments" :key="file.uid" class="feedback-file feedback-file--editable">
              <button type="button" class="feedback-file__link" @click="previewAsset(file)">
                <el-icon><Document /></el-icon>
                {{ file.name }}
              </button>
              <button type="button" class="feedback-file__remove" @click="removeCreateAttachment(index)">删除</button>
            </span>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button @click="saveDraft">保存草稿</el-button>
        <el-button type="primary" :loading="createLoading" @click="submitFeedback">提交反馈</el-button>
      </template>

      <input
        ref="imageInputRef"
        type="file"
        accept="image/*"
        multiple
        class="feedback-hidden-input"
        @change="handleImageSelect"
      />
      <input
        ref="attachmentInputRef"
        type="file"
        accept=".pdf,.xls,.xlsx,.doc,.docx"
        multiple
        class="feedback-hidden-input"
        @change="handleAttachmentSelect"
      />
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowDown,
  ArrowUp,
  ChatDotRound,
  Clock,
  CircleCheckFilled,
  CircleCloseFilled,
  Document,
  Paperclip,
  Picture,
  Plus,
  Search,
  UploadFilled,
  WarningFilled
} from '@element-plus/icons-vue'
import csReplyQuill from '../components/biz/csReplyQuill.vue'
import { uploadFile } from '../api/file'
import { createFeedback, getFeedback, pageFeedback, replyFeedback } from '../api/feedback'
import { sessionState } from '../store/session'
import {
  buildReplyHtml,
  createUid,
  formatTicketTime,
  getAssetName,
  getFileExtension,
  mapTicketStatus,
  normalizeAttachmentList,
  normalizeImageList,
  serializeAssetList,
  resolveAssetUrl,
  TICKET_STATUS_META,
  TICKET_STATUS_OPTIONS,
  toStatusMeta
} from '../utils/ticket'

const DRAFT_KEY = 'workorder.feedback.draft'

const loading = ref(false)
const detailLoading = ref(false)
const createLoading = ref(false)
const replyLoading = ref(false)
const uploadingImages = ref(false)
const uploadingAttachments = ref(false)
const feedbackList = ref([])
const selectedId = ref('')
const selectedDetail = ref(null)
const searchInput = ref('')
const statusFilter = ref('')
const createDialogVisible = ref(false)
const detailExpanded = ref(false)
const replyTextLength = ref(0)
const replyHasContent = ref(false)
const replyHistory = ref(null)
const imageInputRef = ref(null)
const attachmentInputRef = ref(null)
const replyForm = reactive({ content: '' })
const createForm = reactive(createEmptyCreateForm())

const selectedFeedback = computed(() => selectedDetail.value || feedbackList.value.find(item => item.id === selectedId.value) || null)
const canReplySelected = computed(() => !!selectedFeedback.value && !['SOLVED', 'CLOSED'].includes(selectedFeedback.value.status))
const shouldShowDetailToggle = computed(() => !!(selectedFeedback.value && selectedFeedback.value.description && selectedFeedback.value.description.length > 72))
const statusIcon = status => {
  const meta = TICKET_STATUS_META[mapTicketStatus(status)] || TICKET_STATUS_META.PENDING
  const icons = {
    Clock,
    WarningFilled,
    CircleCheckFilled,
    CircleCloseFilled
  }
  return icons[meta.iconName] || Clock
}

watch(
  feedbackList,
  list => {
    if (!list.length) {
      selectedId.value = ''
      selectedDetail.value = null
      return
    }

    const matched = list.find(item => item.id === selectedId.value)
    if (!matched) {
      selectedId.value = list[0].id
    }
  },
  { immediate: true }
)

watch(
  selectedId,
  async value => {
    detailExpanded.value = false
    resetReplyForm()
    if (value) {
      await loadFeedbackDetail(value)
    } else {
      selectedDetail.value = null
    }
    scrollRepliesToLatest()
  }
)

watch(createDialogVisible, visible => {
  if (!visible) {
    return
  }

  restoreDraftFromStorage()
})

function createEmptyCreateForm() {
  return {
    title: '',
    description: '',
    images: [],
    attachments: []
  }
}

function normalizeFeedbackRecord(item = {}) {
  return {
    ...item,
    status: mapTicketStatus(item.status),
    images: normalizeImageList(item.images),
    attachments: normalizeAttachmentList(item.attachments),
    replies: Array.isArray(item.replies)
      ? item.replies.map(reply => ({
          id: reply.id || createUid('reply'),
          role: String(reply.role || 'user').toLowerCase() === 'service' ? 'service' : 'user',
          roleLabel: String(reply.role || 'user').toLowerCase() === 'service' ? '客服' : '我',
          author: reply.author || '用户',
          content: reply.content || '<p><br></p>',
          createdAt: reply.createdAt || '--'
        }))
      : []
  }
}

async function readFileAsDataUrl(file) {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsDataURL(file)
  })
}

function setDraftToStorage() {
  localStorage.setItem(
    DRAFT_KEY,
      JSON.stringify({
        title: createForm.title,
        description: createForm.description,
        images: createForm.images,
        attachments: createForm.attachments
      })
  )
}

function clearDraftStorage() {
  localStorage.removeItem(DRAFT_KEY)
}

function restoreDraftFromStorage() {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) {
      Object.assign(createForm, createEmptyCreateForm())
      return
    }

    const draft = JSON.parse(raw)
    createForm.title = draft.title || ''
    createForm.description = draft.description || ''
    createForm.images = normalizeImageList(draft.images)
    createForm.attachments = normalizeAttachmentList(draft.attachments)
  } catch (error) {
    Object.assign(createForm, createEmptyCreateForm())
  }
}

function resetCreateForm() {
  Object.assign(createForm, createEmptyCreateForm())
}

function resetReplyForm() {
  replyForm.content = ''
  replyTextLength.value = 0
  replyHasContent.value = false
}

async function loadFeedbackList(preferredId = selectedId.value) {
  loading.value = true
  try {
    const res = await pageFeedback({
      keyword: searchInput.value || undefined,
      status: statusFilter.value || undefined,
      pageNum: 1,
      pageSize: 20
    })
    const list = Array.isArray(res?.data?.records) ? res.data.records.map(normalizeFeedbackRecord) : []
    feedbackList.value = list
    const nextSelected = list.find(item => item.id === preferredId) || list[0] || null
    selectedId.value = nextSelected?.id || ''
    if (!selectedId.value) {
      selectedDetail.value = null
    }
  } catch (error) {
    feedbackList.value = []
    selectedId.value = ''
    selectedDetail.value = null
    ElMessage.error(error.message || '反馈列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadFeedbackDetail(id) {
  if (!id) {
    selectedDetail.value = null
    return
  }

  detailLoading.value = true
  try {
    const res = await getFeedback(id)
    selectedDetail.value = res?.data ? normalizeFeedbackRecord(res.data) : null
  } catch (error) {
    selectedDetail.value = null
    ElMessage.error(error.message || '反馈详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function handleSelectFeedback(id) {
  selectedId.value = id
}

function handleSearch() {
  selectedId.value = ''
  loadFeedbackList()
}

function handleReplyEditorState(payload) {
  if (typeof payload?.html === 'string') {
    replyForm.content = payload.html
  }
  replyTextLength.value = payload?.textLength || 0
  replyHasContent.value = Boolean(payload?.hasContent)
}

function openCreateDialog() {
  restoreDraftFromStorage()
  createDialogVisible.value = true
}

function handleDialogClosed() {
  resetCreateForm()
}

async function openImagePicker() {
  imageInputRef.value?.click()
}

async function openAttachmentPicker() {
  attachmentInputRef.value?.click()
}

async function handleImageSelect(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) {
    return
  }

  uploadingImages.value = true
  try {
    const nextItems = []
    for (const file of files) {
      if (createForm.images.length + nextItems.length >= 5) {
        break
      }
      if (!file.type.startsWith('image/')) {
        continue
      }
      const response = await uploadFile(file, 'image')
      const uploaded = response?.data || {}
      const fileUrl = uploaded.imgUrl || uploaded.url || uploaded.fileUrl || ''
      if (!fileUrl) {
        continue
      }
      nextItems.push({
        uid: uploaded.fileId || uploaded.id || createUid('img'),
        name: uploaded.name || file.name || getAssetName(fileUrl),
        url: fileUrl,
        fileUrl: fileUrl,
        serverPath: uploaded.serverPath || fileUrl,
        ext: uploaded.ext || getFileExtension(file.name)
      })
    }
    createForm.images.push(...nextItems)
    setDraftToStorage()
  } catch (error) {
    ElMessage.error(error.message || '图片上传失败')
  } finally {
    uploadingImages.value = false
  }
}

async function handleAttachmentSelect(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) {
    return
  }

  uploadingAttachments.value = true
  try {
    const allowed = ['pdf', 'xls', 'xlsx', 'doc', 'docx']
    const nextItems = []
    for (const file of files) {
      const ext = getFileExtension(file.name)
      if (!allowed.includes(ext)) {
        continue
      }
      const response = await uploadFile(file, 'file')
      const uploaded = response?.data || {}
      const fileUrl = uploaded.url || uploaded.fileUrl || uploaded.imgUrl || ''
      if (!fileUrl) {
        continue
      }
      nextItems.push({
        uid: uploaded.fileId || uploaded.id || createUid('file'),
        name: uploaded.name || file.name,
        url: fileUrl,
        fileUrl: fileUrl,
        serverPath: uploaded.serverPath || fileUrl,
        ext: uploaded.ext || ext
      })
    }
    createForm.attachments.push(...nextItems)
    setDraftToStorage()
  } catch (error) {
    ElMessage.error(error.message || '附件上传失败')
  } finally {
    uploadingAttachments.value = false
  }
}

function removeCreateImage(index) {
  createForm.images.splice(index, 1)
  setDraftToStorage()
}

function removeCreateAttachment(index) {
  createForm.attachments.splice(index, 1)
  setDraftToStorage()
}

function getAssetPreviewUrl(asset) {
  const rawUrl = typeof asset === 'string' ? asset : asset?.url || asset?.fileUrl || asset?.serverPath || ''
  return resolveAssetUrl(rawUrl)
}

function previewAsset(asset) {
  const previewUrl = getAssetPreviewUrl(asset)
  if (!previewUrl) {
    ElMessage.info('当前内容暂不支持预览')
    return
  }
  window.open(previewUrl, '_blank')
}

function handleRichTextClick(event) {
  const target = event.target
  if (target && target.tagName === 'IMG') {
    previewAsset(target.currentSrc || target.src)
  }
}

function renderReplyContent(content) {
  return buildReplyHtml(content)
}

async function submitReply() {
  if (!selectedFeedback.value) {
    return
  }

  if (!replyHasContent.value) {
    ElMessage.warning('请输入回复内容后再发送')
    return
  }

  replyLoading.value = true
  try {
    const currentId = selectedFeedback.value.id
    await replyFeedback(selectedFeedback.value.id, {
      content: buildReplyHtml(replyForm.content),
      author: sessionState.user?.displayName || '我'
    })
    resetReplyForm()
    await loadFeedbackList(currentId)
    await loadFeedbackDetail(currentId)
    scrollRepliesToLatest()
    ElMessage.success('回复已发送')
  } catch (error) {
    ElMessage.error(error.message || '回复发送失败')
  } finally {
    replyLoading.value = false
  }
}

function validateCreateForm() {
  if (!createForm.title.trim()) {
    ElMessage.warning('请输入问题标题')
    return false
  }

  if (!createForm.description.trim()) {
    ElMessage.warning('请输入问题描述')
    return false
  }

  return true
}

function saveDraft() {
  if (!validateCreateForm()) {
    return
  }

  setDraftToStorage()
  createDialogVisible.value = false
  ElMessage.success('草稿已保存到本地')
}

async function submitFeedback() {
  if (!validateCreateForm()) {
    return
  }

  createLoading.value = true
  try {
    const res = await createFeedback({
      title: createForm.title.trim(),
      description: createForm.description.trim(),
      accountName: sessionState.user?.displayName || '',
      images: serializeAssetList(createForm.images),
      attachments: normalizeAttachmentList(createForm.attachments)
    })
    clearDraftStorage()
    createDialogVisible.value = false
    resetCreateForm()
    const createdId = res?.data?.id || ''
    await loadFeedbackList(createdId)
    if (createdId) {
      selectedId.value = createdId
      await loadFeedbackDetail(createdId)
      scrollRepliesToLatest()
    }
    ElMessage.success('反馈已提交')
  } catch (error) {
    ElMessage.error(error.message || '反馈提交失败')
  } finally {
    createLoading.value = false
  }
}

function scrollRepliesToLatest() {
  requestAnimationFrame(() => {
    const container = replyHistory.value
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  })
}

onMounted(async () => {
  await loadFeedbackList()
})
</script>

<style scoped>
.feedback-page {
  min-height: 640px;
  background: linear-gradient(135deg, #eef5ff 0%, #ffffff 65%, #f7f1ff 100%);
  padding-left: 40px;
}

.feedback-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 15px 0 25px;
}

.feedback-page__eyebrow {
  margin: 0 0 4px;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #5d7ea8;
}

.feedback-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1a3870;
}

.feedback-page__create {
  min-width: 120px;
  border-radius: 10px;
  background: linear-gradient(135deg, #17325f 0%, #22457f 100%);
  border-color: transparent;
  margin-right: 12px;
}

.feedback-page__create-icon {
  margin-right: 6px;
}

.feedback-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px;
  margin-bottom: 10px;
  border: 1px solid #e8eef7;
  border-radius: 16px;
  background: #fff;
  box-shadow: -3px 3px 5px rgba(38, 74, 140, 0.075);
}

.feedback-toolbar__search {
  flex: 1;
}

.feedback-toolbar__status {
  width: 220px;
}

.feedback-toolbar__action {
  min-width: 122px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #17325f 0%, #22457f 100%);
  border-color: transparent;
}

.feedback-layout {
  display: grid;
  grid-template-columns: 39% 1fr;
  gap: 16px;
  min-height: 560px;
}

.feedback-detail {
  border: 1px solid #e7edf5;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 16px 40px rgba(26, 56, 112, 0.08);
}

.feedback-list {
  min-height: 100%;
  overflow: hidden;
}

.feedback-card {
  width: 100%;
  padding: 16px;
  margin-bottom: 14px;
  border: none;
  border-radius: 16px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 3px 5px rgba(38, 74, 140, 0.075);
}

.feedback-card:hover,
.feedback-card.is-active {
  border-color: #b9cff5;
  box-shadow: 0 5px 24px rgba(55, 101, 187, 0.16);
  transform: translateY(-1px);
}

.feedback-card__code,
.feedback-detail__code {
  font-size: 13px;
  color: #7b8aa5;
}

.feedback-card__title,
.feedback-detail__title {
  margin-top: 8px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: #16366d;
}

.feedback-card__desc,
.feedback-detail__desc,
.feedback-reply__content,
.feedback-rich-text {
  font-size: 14px;
  line-height: 1.8;
  color: #44536d;
}

.feedback-card__desc {
  display: -webkit-box;
  margin-top: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.feedback-card__footer,
.feedback-reply__meta,
.feedback-composer__actions,
.feedback-detail__code-row,
.feedback-attachment-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.feedback-card__footer {
  margin-top: 14px;
}

.feedback-card__count,
.feedback-card__time {
  font-size: 12px;
  color: #7b8aa5;
}

.feedback-card__count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.feedback-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
}

.feedback-status .el-icon {
  margin-right: 4px;
  font-size: 12px;
}

.feedback-status.is-pending {
  color: #996c00;
  background: #fff7df;
}

.feedback-status.is-processing {
  color: #2c66d6;
  background: #edf4ff;
}

.feedback-status.is-solved {
  color: #2a9a68;
  background: #eaf9f1;
}

.feedback-status.is-closed {
  color: #8f97ab;
  background: #f3f5f9;
}

.feedback-detail {
  display: flex;
  flex-direction: column;
}

.feedback-detail__header,
.feedback-replies,
.feedback-composer,
.feedback-locked {
  padding: 18px 20px;
}

.feedback-detail__header {
  border-bottom: 1px solid #edf1f7;
}

.feedback-detail__code-row {
  align-items: flex-start;
}

.feedback-detail__desc {
  display: -webkit-box;
  margin-top: 10px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.feedback-detail__desc.is-expanded {
  display: block;
}

.feedback-detail__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #2c66d6;
  cursor: pointer;
}

.feedback-assets {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.feedback-assets__block,
.feedback-upload-list__group {
  display: grid;
  gap: 10px;
}

.feedback-assets__label,
.feedback-form-item__label {
  font-size: 13px;
  font-weight: 500;
  color: #4b5872;
}

.feedback-assets__images {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.feedback-assets__image {
  position: relative;
  width: 84px;
  height: 84px;
  padding: 0;
  overflow: hidden;
  border: 1px solid #dbe6f7;
  border-radius: 14px;
  background: #f7faff;
  cursor: pointer;
}

.feedback-assets__image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.feedback-assets__files,
.feedback-reply__files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-assets__files--wrap {
  gap: 10px;
}

.feedback-file {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 0;
  border-radius: 999px;
  background: #f3f7fd;
  color: #466089;
  font-size: 13px;
  cursor: pointer;
}

.feedback-file--editable {
  padding-right: 8px;
}

.feedback-file__link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: inherit;
  cursor: pointer;
}

.feedback-file__remove {
  padding: 0;
  border: 0;
  background: transparent;
  color: #2c66d6;
  cursor: pointer;
}

.feedback-replies {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.feedback-replies__title {
  margin-bottom: 14px;
  font-size: 16px;
  font-weight: 600;
  color: #193867;
}

.feedback-replies__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 280px;
  overflow-y: auto;
  padding-right: 4px;
}

.feedback-reply {
  padding: 14px 16px;
  border: 1px solid #edf1f7;
  border-radius: 14px;
  background: #fff;
}

.feedback-reply.is-service {
  background: linear-gradient(135deg, #eff5ff 0%, #e8f1ff 100%);
}

.feedback-reply__author {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #17325f;
  font-weight: 500;
}

.feedback-reply.is-service .feedback-reply__author {
  color: #2d67d8;
}

.feedback-reply__meta {
  margin-bottom: 10px;
  font-size: 12px;
  color: #7a88a3;
}

.feedback-reply__tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 8px;
  border-radius: 5px;
  background: #2d67d8;
  color: #fff;
  font-size: 12px;
}

.feedback-reply__author .feedback-reply__tag + .feedback-reply__tag {
  display: none;
}

.feedback-reply__tag.is-user {
  background: #e5eefb;
  color: #34547d;
}

.feedback-composer {
  border-top: 1px solid #edf1f7;
}

.feedback-composer__editor {
  margin-top: 14px;
  width: 100%;
  min-width: 0;
}

.feedback-composer__tools {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.feedback-composer__tip {
  font-size: 13px;
  color: #7b8aa5;
}

.feedback-composer__submit.el-button--primary {
  background: #17325f !important;
  border-color: #17325f !important;
  color: #fff !important;
  border-radius: 10px;
}

.feedback-locked,
.feedback-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 220px;
  padding: 20px;
  color: #8593ad;
  text-align: center;
}

.feedback-empty--page {
  min-height: 420px;
  border: 1px dashed #d8e3f4;
  border-radius: 18px;
  background: linear-gradient(135deg, #fbfdff 0%, #f5f8ff 100%);
}

.feedback-empty--detail {
  min-height: 560px;
}

.feedback-empty__text {
  margin: 0;
  line-height: 1.8;
}

.feedback-dialog {
  display: grid;
  gap: 18px;
}

.feedback-dialog__section-title {
  font-size: 18px;
  font-weight: 600;
  color: #193867;
}

.feedback-form-item {
  display: grid;
  gap: 10px;
}

.feedback-form-item__label.is-required::before {
  content: '*';
  margin-right: 4px;
  color: #f56c6c;
}

.feedback-tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid #d6e2f6;
  border-radius: 10px;
  background: #fff;
  color: #274d89;
  cursor: pointer;
}

.feedback-tool:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.feedback-tool__hint {
  font-size: 12px;
  color: #7b8aa5;
}

.feedback-hidden-input {
  display: none;
}

.feedback-rich-text {
  word-break: break-word;
}

.feedback-rich-text :deep(p) {
  margin: 0 0 8px;
}

.feedback-rich-text :deep(p:last-child) {
  margin-bottom: 0;
}

.feedback-rich-text :deep(img) {
  display: block;
  max-width: 220px;
  border-radius: 14px;
  cursor: zoom-in;
}

.feedback-rich-text :deep(.cs-reply-attachment),
.feedback-rich-text :deep(.ql-attachment) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  max-width: 100%;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf2ff;
  color: #2f6fe4;
  font-size: 12px;
  line-height: 1.4;
  vertical-align: middle;
}

.feedback-rich-text :deep(.cs-reply-attachment__icon),
.feedback-rich-text :deep(.ql-attachment__icon) {
  display: none;
}

.feedback-rich-text :deep(.cs-reply-attachment__name),
.feedback-rich-text :deep(.ql-attachment__name) {
  color: inherit;
  text-decoration: none;
  word-break: break-all;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.el-dialog) {
  border-radius: 18px;
  overflow: hidden;
}

:deep(.el-dialog__header) {
  padding: 20px 24px 12px;
  border-bottom: 1px solid #edf1f7;
}

:deep(.el-dialog__title) {
  font-size: 24px;
  font-weight: 600;
  color: #193867;
}

:deep(.el-dialog__body) {
  padding: 20px 24px 12px;
}

:deep(.el-dialog__footer) {
  padding: 16px 24px 24px;
}

:deep(.el-textarea__inner),
:deep(.el-input__inner) {
  border-radius: 12px;
}

@media (max-width: 960px) {
  .feedback-page {
    padding-left: 0;
  }

  .feedback-page__header,
  .feedback-toolbar,
  .feedback-composer__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .feedback-toolbar__status {
    width: 100%;
  }

  .feedback-layout {
    grid-template-columns: 1fr;
  }
}
</style>
