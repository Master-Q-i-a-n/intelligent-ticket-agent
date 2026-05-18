<template>
  <section class="work-order-page" v-loading="loading">
    <div class="work-order-page__header">
      <div>
        <p class="work-order-page__eyebrow">工单管理</p>
        <h2 class="work-order-page__title">处理和回复用户提交的工单</h2>
      </div>
    </div>

    <div class="work-order-stats">
      <div v-for="item in statCards" :key="item.key" class="work-order-stat" :class="item.className">
        <div class="work-order-stat__label">{{ item.label }}</div>
        <div class="work-order-stat__value">{{ item.value }}</div>
      </div>
    </div>

    <div class="work-order-toolbar">
      <el-input
        v-model.trim="queryForm.keyword"
        clearable
        placeholder="搜索工单标题、描述、编号或账号名称"
        class="work-order-toolbar__search"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

       <el-select
        v-model="queryForm.category"
        clearable
        placeholder="全部工单分类"
        class="work-order-toolbar__filter"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_CATEGORY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-select
        v-model="queryForm.priority"
        clearable
        placeholder="全部优先级"
        class="work-order-toolbar__filter"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_PRIORITY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-select
        v-model="queryForm.serviceGroup"
        clearable
        placeholder="全部客服组"
        class="work-order-toolbar__filter"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_SERVICE_GROUP_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-select
        v-model="queryForm.status"
        clearable
        placeholder="全部状态"
        class="work-order-toolbar__status"
        @change="handleSearch"
      >
        <el-option v-for="item in TICKET_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>

      <el-button type="primary" class="work-order-toolbar__button" @click="handleSearch">查询</el-button>
    </div>

      <div class="work-order-table">
        <el-table :data="workOrderList" row-key="id" stripe>
        <el-table-column label="序号" width="72">
          <template #default="{ $index }">
            {{ (page.pageNum - 1) * page.pageSize + $index + 1 }}
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编号" width="120" />
        <el-table-column prop="title" label="标题" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="work-order-table__title">{{ row.title }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="assignee" label="处理人" width="160" />
        <el-table-column label="分类" width="120">
          <template #default="{ row }">
            <span class="work-order-category">{{ row.category || '--' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="客服组" width="130">
          <template #default="{ row }">
            <span class="work-order-category">{{ toServiceGroupMeta(row.serviceGroup).label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="优先级" width="100">
          <template #default="{ row }">
            <span class="work-order-priority" :class="toPriorityMeta(row.priority).className">
              {{ toPriorityMeta(row.priority).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <span class="work-order-status" :class="toStatusMeta(row.status).className">
              {{ toStatusMeta(row.status).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" class="work-order-table__action" @click="openDetailDialog(row.id)">
              详情
            </el-button>
          </template>
          </el-table-column>
        </el-table>
        <div class="work-order-pagination">
          <el-pagination
            v-model:current-page="page.pageNum"
            v-model:page-size="page.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="page.total"
            background
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handleCurrentChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>

    <el-dialog
      v-model="detailDialogVisible"
      title="工单详情"
      width="920px"
      append-to-body
      :close-on-click-modal="false"
      @closed="handleDialogClosed"
    >
      <template v-if="selectedWorkOrder">
        <div class="work-order-detail" v-loading="detailLoading">
          <div class="work-order-detail__header">
            <div class="work-order-detail__code">{{ selectedWorkOrder.code }}</div>
            <h3 class="work-order-detail__title">{{ selectedWorkOrder.title }}</h3>

            <div class="work-order-detail__description" :class="{ 'is-expanded': detailExpanded }">
              {{ selectedWorkOrder.description }}
            </div>

            <button
              v-if="shouldShowDescriptionToggle"
              type="button"
              class="work-order-detail__toggle"
              @click="detailExpanded = !detailExpanded"
            >
              {{ detailExpanded ? '收起' : '更多' }}
              <el-icon>
                <component :is="detailExpanded ? ArrowUp : ArrowDown" />
              </el-icon>
            </button>

            <div class="work-order-detail__meta">
              <div class="work-order-detail__meta-item">
                <el-icon><User /></el-icon>
                <span>{{ selectedWorkOrder.accountName || selectedWorkOrder.assignee || '--' }}</span>
              </div>
              <div class="work-order-detail__meta-item">
                <el-icon><Clock /></el-icon>
                <span>创建：{{ formatTicketTime(selectedWorkOrder.createdAt) }}</span>
              </div>
              <div class="work-order-detail__meta-item">
                <el-icon><Clock /></el-icon>
                <span>更新：{{ formatTicketTime(selectedWorkOrder.updatedAt) }}</span>
              </div>
              <div class="work-order-detail__meta-item">
                <el-icon><Paperclip /></el-icon>
                <span>附件：</span>
                <div class="work-order-detail__attachments">
                  <button
                    v-for="file in selectedWorkOrder.attachments"
                    :key="file.uid"
                    type="button"
                    class="work-order-detail__attachment"
                    @click="previewAsset(file)"
                  >
                    {{ file.name }}
                  </button>
                  <span v-if="!selectedWorkOrder.attachments.length">无</span>
                </div>
              </div>
            </div>

            <div v-if="selectedWorkOrder.images.length" class="work-order-detail__images-block">
              <div class="work-order-detail__section-title">问题图片</div>
              <div class="work-order-detail__images">
                <button
                  v-for="image in selectedWorkOrder.images"
                  :key="image.uid"
                  type="button"
                  class="work-order-image"
                  @click="previewAsset(image)"
                >
                  <img :src="getAssetPreviewUrl(image)" :alt="image.name" />
                </button>
              </div>
            </div>

            <div class="work-order-detail__status">
              <div class="work-order-detail__section-title">工单状态</div>
              <div class="work-order-detail__status-list">
                <button
                  v-for="item in TICKET_STATUS_OPTIONS"
                  :key="item.value"
                  type="button"
                  class="work-order-detail__status-item"
                  :class="[
                    toStatusMeta(item.value).className,
                    {
                      'is-active': selectedWorkOrder.status === item.value,
                      'is-disabled': isStatusActionDisabled(item.value)
                    }
                  ]"
                  :disabled="isStatusActionDisabled(item.value)"
                  @click="updateWorkOrderStatusAction(item.value)"
                >
                  <el-icon><component :is="statusIcon(item.value)" /></el-icon>
                  <span>{{ item.label }}</span>
                </button>
              </div>
            </div>
          </div>

          <div class="work-order-detail__body">
            <div class="work-order-reply-record">
              <div class="work-order-detail__section-title">回复记录（{{ selectedWorkOrder.replies.length }}）</div>
              <div ref="replyHistory" class="work-order-reply-record__list">
                <div
                  v-for="reply in selectedWorkOrder.replies"
                  :key="reply.id"
                  class="work-order-reply-record__item"
                  :class="{ 'is-service': reply.role === 'service' }"
                >
                  <div class="work-order-reply-record__item-top">
                    <div class="work-order-reply-record__author">
                      <span>{{ reply.author }}</span>
                    <span
                      class="work-order-reply-record__tag"
                      :class="{ 'is-user': reply.role !== 'service' }"
                    >
                      {{ getReplyRoleLabel(reply.role) }}
                    </span>
                    </div>
                    <span>{{ formatTicketTime(reply.createdAt) }}</span>
                  </div>

                  <div
                    class="work-order-reply-record__content work-order-rich-text"
                    v-html="renderReplyContent(reply.content)"
                    @click="handleRichTextClick"
                  ></div>
                  </div>
              </div>
            </div>

            <div class="work-order-ai-analysis">
              <div class="work-order-ai-analysis__header">
                <div class="work-order-ai-analysis__header-title">
                  <span class="work-order-ai-analysis__header-icon"></span>
                  <span>AI 智能分析</span>
                </div>
                <el-button
                  size="small"
                  type="primary"
                  class="work-order-ai-analysis__refresh"
                  :loading="analysisRefreshLoading"
                  @click="refreshSelectedAnalysis"
                >
                  刷新分析
                </el-button>
              </div>

              <div class="work-order-ai-analysis__grid">
                <div class="work-order-ai-analysis__card">
                  <div class="work-order-ai-analysis__card-title">
                    <span class="work-order-ai-analysis__card-icon">📊</span>
                    <span>AI 分类结果</span>
                  </div>
                  <div class="work-order-ai-analysis__card-body">
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">类型</span>
                      <span class="work-order-ai-analysis__tag work-order-ai-analysis__tag--blue">{{ selectedWorkOrder.category }}</span>
                    </div>
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">客服组</span>
                      <span class="work-order-ai-analysis__tag work-order-ai-analysis__tag--blue">{{ toServiceGroupMeta(selectedWorkOrder.serviceGroup).label }}</span>
                    </div>
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">优先级</span>
                      <span class="work-order-priority" :class="toPriorityMeta(selectedWorkOrder.priority).className">
                        {{ toPriorityMeta(selectedWorkOrder.priority).label }}
                      </span>
                    </div>
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">置信度</span>
                      <span class="work-order-ai-analysis__tag work-order-ai-analysis__tag--green">自动分类</span>
                    </div>
                  </div>
                </div>

                <div class="work-order-ai-analysis__card">
                  <div class="work-order-ai-analysis__card-title">
                    <span class="work-order-ai-analysis__card-icon">💬</span>
                    <span>AI 情感分析</span>
                  </div>
                  <div class="work-order-ai-analysis__card-body">
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">情绪</span>
                      <span class="work-order-ai-analysis__tag work-order-ai-analysis__tag--blue">{{ selectedWorkOrder.emotion }}</span>
                    </div>
                    <div class="work-order-ai-analysis__row">
                      <span class="work-order-ai-analysis__label">情绪得分</span>
                    </div>
                    <div class="work-order-ai-analysis__progress-row">
                      <div class="work-order-ai-analysis__progress">
                        <div class="work-order-ai-analysis__progress-bar" style="width: 50%; background: #67c23a;"></div>
                      </div>
                      <span class="work-order-ai-analysis__progress-value">50%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="canReplySelected" class="work-order-composer">
              <div class="work-order-composer__header">
                <div class="work-order-detail__section-title">回复用户</div>
                <el-button
                  size="small"
                  type="primary"
                  :loading="aiReplyLoading"
                  @click="generateAiReplySuggestion"
                >
                  AI 建议
                </el-button>
              </div>
              <cs-reply-quill
                ref="replyEditor"
                v-model="replyForm.content"
                class="work-order-composer__editor"
                placeholder="请输入回复内容..."
                :max-length="500"
                @state-change="handleReplyEditorState"
              />

              <div v-if="aiReplyCaseSources.length" class="work-order-composer__cases">
                <div class="work-order-composer__cases-title">参考历史案例</div>
                <div class="work-order-composer__cases-list">
                  <div
                    v-for="item in aiReplyCaseSources"
                    :key="item.ticketId"
                    class="work-order-composer__case"
                  >
                    <span class="work-order-composer__case-code">{{ item.ticketCode || item.ticketId }}</span>
                    <span class="work-order-composer__case-title">{{ item.title || '--' }}</span>
                    <span class="work-order-composer__case-score">相似度 {{ formatSimilarity(item.similarityScore) }}</span>
                  </div>
                </div>
              </div>

              <div class="work-order-composer__actions">
                <div class="work-order-composer__tools">
                <span class="work-order-composer__tip">正文内容 {{ replyTextLength }}/500 字</span>
                </div>
                <el-button type="primary" class="work-order-composer__submit" :loading="replyLoading" @click="submitReply">
                  发送回复
                </el-button>
              </div>
            </div>

            <div v-else class="work-order-locked">
              当前工单状态为“{{ toStatusMeta(selectedWorkOrder.status).label }}”，已关闭回复入口。
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="work-order-locked">请选择一条工单查看详情。</div>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown,
  ArrowUp,
  Clock,
  CircleCheckFilled,
  CircleCloseFilled,
  Paperclip,
  Search,
  User,
  WarningFilled
} from '@element-plus/icons-vue'
import csReplyQuill from '../components/biz/csReplyQuill.vue'
import request from '../api/http'
import {
  getSuggestion,
  getWorkOrderDetail,
  getWorkOrderSummary,
  pageWorkOrders,
  refreshWorkOrderAnalysis,
  replyWorkOrder,
  updateWorkOrderStatus
} from '../api/workOrder'
import { sessionState } from '../store/session'
import {
  buildReplyHtml,
  formatTicketTime,
  getAssetName,
  getFileExtension,
  getReplyRoleLabel,
  mapTicketStatus,
  normalizeAttachmentList,
  normalizeImageList,
  resolveAssetUrl,
  TICKET_STATUS_META,
  TICKET_STATUS_OPTIONS,
  TICKET_PRIORITY_OPTIONS,
  TICKET_CATEGORY_OPTIONS,
  TICKET_SERVICE_GROUP_OPTIONS,
  toStatusMeta,
  toPriorityMeta,
  toServiceGroupMeta
} from '../utils/ticket'

const loading = ref(false)
const detailLoading = ref(false)
const replyLoading = ref(false)
const aiReplyLoading = ref(false)
const aiReplyCaseSources = ref([])
const analysisRefreshLoading = ref(false)
const workOrderList = ref([])
const detailDialogVisible = ref(false)
const selectedId = ref('')
const selectedDetail = ref(null)
const detailExpanded = ref(false)
const replyTextLength = ref(0)
const replyHasContent = ref(false)
const replyHistory = ref(null)
const replyForm = reactive({ content: '' })
const page = reactive({ pageNum: 1, pageSize: 20, total: 0 })
const queryForm = reactive({ keyword: '', category: '', priority: '', serviceGroup: '', status: '' })
const summary = reactive({ total: 0, pending: 0, processing: 0, solved: 0, closed: 0 })

const selectedWorkOrder = computed(() => selectedDetail.value || workOrderList.value.find(item => item.id === selectedId.value) || null)
const canReplySelected = computed(() => !!selectedWorkOrder.value && !['SOLVED', 'CLOSED'].includes(selectedWorkOrder.value.status))
const shouldShowDescriptionToggle = computed(() => !!(selectedWorkOrder.value && selectedWorkOrder.value.description && selectedWorkOrder.value.description.length > 72))
const statCards = computed(() => [
  { key: 'all', label: '工单总数', value: summary.total, className: 'is-total' },
  { key: 'pending', label: '待处理', value: summary.pending, className: 'is-pending' },
  { key: 'processing', label: '处理中', value: summary.processing, className: 'is-processing' },
  { key: 'solved', label: '已解决', value: summary.solved, className: 'is-solved' },
  { key: 'closed', label: '已关闭', value: summary.closed, className: 'is-closed' }
])

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
  workOrderList,
  list => {
    if (!list.length) {
      selectedId.value = ''
      selectedDetail.value = null
      return
    }

    if (selectedId.value && !list.some(item => item.id === selectedId.value)) {
      selectedId.value = ''
      selectedDetail.value = null
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
      await loadWorkOrderDetail(value)
    } else {
      selectedDetail.value = null
    }
    scrollRepliesToLatest()
  }
)

function normalizeWorkOrderRecord(item = {}) {
  return {
    id: item.id,
    code: item.code,
    title: item.title,
    description: item.description,
    category: item.category || '',
    serviceGroup: item.serviceGroup || 'PRODUCT_CONSULTING',
    priority: item.priority || 'MEDIUM',
    emotion: item.emotion || '无',
    status: mapTicketStatus(item.status),
    assignee: item.assignee || '未分配',
    accountName: item.accountName || item.assignee || '未分配',
    createdAt: formatTicketTime(item.createdAt),
    updatedAt: formatTicketTime(item.updatedAt),
    images: normalizeImageList(item.images),
    attachments: normalizeAttachmentList(item.attachments),
    replies: Array.isArray(item.replies)
      ? item.replies.map(reply => ({
          id: reply.id,
          role: String(reply.role || 'user').toLowerCase() === 'service' ? 'service' : 'user',
          author: reply.author || '用户',
          content: reply.content || '<p><br></p>',
          createdAt: reply.createdAt || '--'
        }))
      : []
  }
}

async function loadWorkOrders() {
  loading.value = true
  try {
    const params = {
      keyword: queryForm.keyword || undefined,
      category: queryForm.category || undefined,
      priority: queryForm.priority || undefined,
      serviceGroup: queryForm.serviceGroup || undefined,
      status: queryForm.status || undefined,
      pageNum: page.pageNum,
      pageSize: page.pageSize
    }
    const [listRes, summaryRes] = await Promise.all([
      pageWorkOrders(params),
      getWorkOrderSummary({
        keyword: queryForm.keyword || undefined,
        status: queryForm.status || undefined
      })
    ])
    const res = listRes
    const records = Array.isArray(res?.data?.records) ? res.data.records.map(normalizeWorkOrderRecord) : []
    workOrderList.value = records
    page.total = Number(res?.data?.total || records.length) || 0
    const summaryData = summaryRes?.data || {}
    summary.total = Number(summaryData.total || 0) || 0
    summary.pending = Number(summaryData.pending || 0) || 0
    summary.processing = Number(summaryData.processing || 0) || 0
    summary.solved = Number(summaryData.solved || 0) || 0
    summary.closed = Number(summaryData.closed || 0) || 0
  } catch (error) {
    workOrderList.value = []
    page.total = 0
    summary.total = 0
    summary.pending = 0
    summary.processing = 0
    summary.solved = 0
    summary.closed = 0
    selectedId.value = ''
    selectedDetail.value = null
    ElMessage.error(error.message || '工单列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadWorkOrderDetail(id) {
  if (!id) {
    selectedDetail.value = null
    return
  }

  detailLoading.value = true
  try {
    const res = await getWorkOrderDetail(id)
    selectedDetail.value = res?.data ? normalizeWorkOrderRecord(res.data) : null
  } catch (error) {
    selectedDetail.value = null
    ElMessage.error(error.message || '工单详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function countByStatus(status) {
  return workOrderList.value.filter(item => item.status === status).length
}

function handleSearch() {
  page.pageNum = 1
  selectedId.value = ''
  loadWorkOrders()
}

function handleCurrentChange(value) {
  page.pageNum = value
  loadWorkOrders()
}

function handleSizeChange(value) {
  page.pageSize = value
  page.pageNum = 1
  loadWorkOrders()
}

function openDetailDialog(id) {
  selectedId.value = id
  detailDialogVisible.value = true
}

function handleDialogClosed() {
  detailExpanded.value = false
  resetReplyForm()
}

function isStatusActionDisabled(status) {
  if (!selectedWorkOrder.value) {
    return true
  }

  if (selectedWorkOrder.value.status === 'SOLVED' || selectedWorkOrder.value.status === 'CLOSED') {
    return true
  }

  return status === 'PENDING' || status === 'PROCESSING'
}

async function updateWorkOrderStatusAction(status) {
  if (!selectedWorkOrder.value || selectedWorkOrder.value.status === status || isStatusActionDisabled(status)) {
    return
  }

  try {
    await ElMessageBox.confirm('确认将工单状态变更为“' + toStatusMeta(status).label + '”吗？变更后可在详情中继续查看记录。', '状态确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch (error) {
    return
  }

  try {
    const currentId = selectedWorkOrder.value.id
    await updateWorkOrderStatus(selectedWorkOrder.value.id, { status, remark: '' })
    await loadWorkOrders()
    await loadWorkOrderDetail(currentId)
    ElMessage.success('工单状态已更新')
  } catch (error) {
    ElMessage.error(error.message || '工单状态更新失败')
  }
}

function handleReplyEditorState(payload) {
  if (typeof payload?.html === 'string') {
    replyForm.content = payload.html
  }
  replyTextLength.value = payload?.textLength || 0
  replyHasContent.value = Boolean(payload?.hasContent)
}

function resetReplyForm() {
  replyForm.content = ''
  replyTextLength.value = 0
  replyHasContent.value = false
  aiReplyCaseSources.value = []
}

function renderReplyContent(content) {
  return buildReplyHtml(content)
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

function scrollRepliesToLatest() {
  requestAnimationFrame(() => {
    const container = replyHistory.value
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  })
}

async function generateAiReplySuggestion() {
  if (!selectedWorkOrder.value || !canReplySelected.value || aiReplyLoading.value) {
    return
  }

  if (replyHasContent.value) {
    try {
      await ElMessageBox.confirm('当前回复框已有内容，是否用 AI 建议替换？', '替换确认', {
        confirmButtonText: '替换',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch (error) {
      return
    }
  }

  aiReplyLoading.value = true
  aiReplyCaseSources.value = []
  try {
    const res = await getSuggestion(selectedWorkOrder.value.id)
    const suggestion = res?.data?.suggestedReply
    if (!suggestion) {
      ElMessage.warning('AI 回复建议为空')
      return
    }

    replyForm.content = buildReplyHtml(suggestion)
    aiReplyCaseSources.value = Array.isArray(res?.data?.sourceTemplates) ? res.data.sourceTemplates : []
    ElMessage.success('AI 回复建议已生成')
  } catch (error) {
    ElMessage.error(error.message || 'AI 回复建议生成失败')
  } finally {
    aiReplyLoading.value = false
  }
}

function formatSimilarity(value) {
  const score = Number(value)
  if (!Number.isFinite(score)) {
    return '--'
  }
  return `${Math.round(score * 100)}%`
}

async function refreshSelectedAnalysis() {
  if (!selectedWorkOrder.value || analysisRefreshLoading.value) {
    return
  }

  analysisRefreshLoading.value = true
  try {
    const currentId = selectedWorkOrder.value.id
    await refreshWorkOrderAnalysis(currentId)
    await loadWorkOrders()
    await loadWorkOrderDetail(currentId)
    ElMessage.success('AI 分析已刷新')
  } catch (error) {
    ElMessage.error(error.message || 'AI 分析刷新失败')
  } finally {
    analysisRefreshLoading.value = false
  }
}

async function submitReply() {
  if (!selectedWorkOrder.value || !canReplySelected.value) {
    return
  }

  if (!replyHasContent.value) {
    ElMessage.warning('请输入回复内容后再发送')
    return
  }

  replyLoading.value = true
  try {
    const currentId = selectedWorkOrder.value.id
    await replyWorkOrder(selectedWorkOrder.value.id, {
      content: buildReplyHtml(replyForm.content),
      author: sessionState.user?.displayName || '客服'
    })
    resetReplyForm()
    await loadWorkOrders()
    await loadWorkOrderDetail(currentId)
    scrollRepliesToLatest()
    ElMessage.success('回复已发送')
  } catch (error) {
    ElMessage.error(error.message || '回复发送失败')
  } finally {
    replyLoading.value = false
  }
}

onMounted(async () => {
  await loadWorkOrders()
})
</script>

<style scoped>
.work-order-page {
  width: 100%;
  max-width: 100%;
  min-height: calc(100vh - 64px);
  margin: 0;
  padding: 0 40px 32px;
  background: linear-gradient(135deg, #eef5ff 0%, #ffffff 65%, #f7f1ff 100%);
  box-sizing: border-box;
  overflow-x: hidden;
}

.work-order-page__header {
  display: flex;
  align-items: center;
  padding: 15px 0 25px;
}

.work-order-page__eyebrow {
  margin: 0 0 4px;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #5d7ea8;
}

.work-order-page__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1b3769;
}

.work-order-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
  min-width: 0;
}

.work-order-stat {
  padding: 14px 16px 12px;
  border: 2px solid #dce4f0;
  border-radius: 12px;
  background: #fff;
}

.work-order-stat.is-total {
  border-color: #20375e;
}

.work-order-stat.is-pending {
  border-color: #f3b123;
}

.work-order-stat.is-processing {
  border-color: #3a86ff;
}

.work-order-stat.is-solved {
  border-color: #1cc965;
}

.work-order-stat.is-closed {
  border-color: #9da8ba;
}

.work-order-stat__label {
  font-size: 13px;
  color: #5f6d85;
}

.work-order-stat__value {
  margin-top: 8px;
  font-size: 33px;
  font-weight: 600;
  line-height: 1;
  color: #20375e;
}

.work-order-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.work-order-toolbar__search {
  flex: 1;
}

.work-order-toolbar__filter {
  width: 220px;
}

.work-order-toolbar__status {
  width: 220px;
}

.work-order-toolbar__button {
  min-width: 86px;
  border-radius: 8px;
  background: #2d66ea;
  border-color: #2d66ea;
}


.work-order-table {
  border: 1px solid #edf1f7;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8px 24px rgba(39, 78, 136, 0.05);
  overflow: hidden;
  min-width: 0;
}

.work-order-table :deep(.el-table) {
  width: 100%;
  min-width: 0;
}

.work-order-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 18px 18px;
}

.work-order-table__title {
  display: block;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #17325f;
  font-weight: 500;
}

.work-order-table__action {
  padding: 0;
}

.work-order-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 66px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1;
}

.work-order-status.is-pending,
.work-order-detail__status-item.is-pending {
  color: #996c00;
  background: #fff7df;
}

.work-order-status.is-processing,
.work-order-detail__status-item.is-processing {
  color: #2d66ea;
  background: #eaf2ff;
}

.work-order-status.is-solved,
.work-order-detail__status-item.is-solved {
  color: #17995c;
  background: #e8faef;
}

.work-order-status.is-closed,
.work-order-detail__status-item.is-closed {
  color: #7f8898;
  background: #f1f3f7;
}

.work-order-category {
  color: #606266;
  font-size: 13px;
}

.work-order-priority {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 18px;
}

.work-order-priority.is-low {
  color: #67c23a;
  background: #f0f9eb;
}

.work-order-priority.is-medium {
  color: #409eff;
  background: #ecf5ff;
}

.work-order-priority.is-high {
  color: #e6a23c;
  background: #fdf6ec;
}

.work-order-priority.is-urgent {
  color: #f56c6c;
  background: #fef0f0;
}

.work-order-detail {
  border: 1px solid #ebeff6;
  border-radius: 28px;
  background: #fff;
  overflow: hidden;
}

.work-order-detail__header {
  padding: 26px 28px 18px;
}

.work-order-detail__code {
  font-size: 14px;
  color: #7b89a3;
}

.work-order-detail__title {
  margin: 10px 0 0;
  font-size: 31px;
  font-weight: 600;
  color: #17325f;
}

.work-order-detail__description {
  display: -webkit-box;
  margin-top: 14px;
  overflow: hidden;
  font-size: 15px;
  line-height: 1.9;
  color: #44536d;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.work-order-detail__description.is-expanded {
  display: block;
}

.work-order-detail__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  margin-top: 8px;
  border: 0;
  background: transparent;
  color: #2d66ea;
  cursor: pointer;
}

.work-order-detail__meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 18px;
  margin-top: 18px;
}

.work-order-detail__meta-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: #50607c;
}

.work-order-detail__attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.work-order-detail__attachment {
  padding: 0;
  border: 0;
  background: transparent;
  color: #2d66ea;
  cursor: pointer;
}

.work-order-detail__images-block,
.work-order-detail__status {
  margin-top: 20px;
}

.work-order-detail__section-title {
  font-size: 18px;
  font-weight: 600;
  color: #17325f;
}

.work-order-detail__images {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 84px));
  gap: 10px;
  margin-top: 12px;
}

.work-order-detail__status-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.work-order-detail__status-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border: 1px solid #dfe6f2;
  border-radius: 8px;
  cursor: pointer;
}

.work-order-detail__status-item.is-active {
  border-color: currentColor;
  box-shadow: inset 0 0 0 1px currentColor;
}

.work-order-detail__status-item.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.work-order-detail__body {
  border-top: 1px solid #edf1f7;
}

.work-order-reply-record,
.work-order-composer,
.work-order-locked {
  padding: 18px 28px 22px;
}

.work-order-reply-record__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 320px;
  margin-top: 14px;
  overflow-y: auto;
  padding-right: 4px;
}

.work-order-reply-record__item {
  padding: 16px 18px;
  border: 1px solid #e7edf6;
  border-radius: 12px;
  background: #fff;
}

.work-order-reply-record__item.is-service {
  background: #edf5ff;
  border-color: #b9d4ff;
}

.work-order-reply-record__item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  font-size: 12px;
  color: #7c89a0;
}

.work-order-reply-record__author {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #17325f;
  font-weight: 500;
}

.work-order-reply-record__tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: #2d66ea;
  color: #fff;
  font-size: 12px;
}

.work-order-reply-record__author .work-order-reply-record__tag + .work-order-reply-record__tag {
  display: none;
}

.work-order-reply-record__tag.is-user {
  background: #e5eefb;
  color: #34547d;
}

.work-order-reply-record__content {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.9;
  color: #33425c;
}

.work-order-composer {
  border-top: 1px solid #edf1f7;
}

.work-order-composer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.work-order-composer__editor {
  margin-top: 14px;
}

.work-order-composer__cases {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #dfe8f5;
  border-radius: 10px;
  background: #f7faff;
}

.work-order-composer__cases-title {
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #17325f;
}

.work-order-composer__cases-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.work-order-composer__case {
  display: grid;
  grid-template-columns: minmax(96px, auto) minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}

.work-order-composer__case-code {
  color: #2d66ea;
  font-weight: 600;
}

.work-order-composer__case-title {
  min-width: 0;
  overflow: hidden;
  color: #44536d;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-order-composer__case-score {
  color: #7f8ba0;
}

.work-order-composer__actions {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  margin-top: 16px;
}

.work-order-composer__tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.work-order-composer__tip {
  font-size: 12px;
  color: #7f8ba0;
}

.work-order-composer__submit {
  min-width: 110px;
  border-radius: 10px;
  background: #203a62;
  border-color: #203a62;
}

.work-order-locked {
  font-size: 14px;
  color: #7f8ba0;
  text-align: center;
}

.work-order-image {
  position: relative;
  width: 84px;
  height: 84px;
  padding: 0;
  border: 1px solid #d9e4f3;
  border-radius: 12px;
  overflow: hidden;
  background: #f7faff;
  cursor: pointer;
}

.work-order-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.work-order-rich-text {
  word-break: break-word;
}

.work-order-rich-text :deep(p) {
  margin: 0 0 8px;
}

.work-order-rich-text :deep(p:last-child) {
  margin-bottom: 0;
}

.work-order-rich-text :deep(img) {
  display: block;
  max-width: 220px;
  border-radius: 14px;
  cursor: zoom-in;
}

.work-order-rich-text :deep(.cs-reply-attachment),
.work-order-rich-text :deep(.ql-attachment) {
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

.work-order-rich-text :deep(.cs-reply-attachment__icon),
.work-order-rich-text :deep(.ql-attachment__icon) {
  display: none;
}

.work-order-rich-text :deep(.cs-reply-attachment__name),
.work-order-rich-text :deep(.ql-attachment__name) {
  color: inherit;
  text-decoration: none;
  word-break: break-all;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-order-ai-analysis {
  margin: 20px 0;
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  padding: 16px 20px;
}

.work-order-ai-analysis__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f2f7;
}

.work-order-ai-analysis__header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.work-order-ai-analysis__header-icon {
  font-size: 18px;
}

.work-order-ai-analysis__refresh {
  border-radius: 8px;
}

.work-order-ai-analysis__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.work-order-ai-analysis__card {
  background: #fafbfd;
  border: 1px solid #eef1f6;
  border-radius: 10px;
  padding: 14px 18px;
}

.work-order-ai-analysis__card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #555;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8ecf2;
}

.work-order-ai-analysis__card-icon {
  font-size: 14px;
}

.work-order-ai-analysis__card-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.work-order-ai-analysis__row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.work-order-ai-analysis__label {
  color: #8c95a6;
  min-width: 60px;
}

.work-order-ai-analysis__tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
}

.work-order-ai-analysis__tag--blue {
  background: #e8f4fd;
  color: #409eff;
}

.work-order-ai-analysis__tag--gray {
  background: #f0f2f5;
  color: #909399;
}

.work-order-ai-analysis__tag--green {
  background: #e8f8e8;
  color: #67c23a;
}

.work-order-ai-analysis__progress-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.work-order-ai-analysis__progress {
  flex: 1;
  height: 8px;
  background: #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.work-order-ai-analysis__progress-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.work-order-ai-analysis__progress-value {
  font-size: 12px;
  color: #909399;
  min-width: 36px;
  text-align: right;
}

:deep(.el-table th) {
  background: #f8fafc;
  color: #66748b;
  font-weight: 600;
}

:deep(.el-dialog) {
  border-radius: 26px;
  overflow: hidden;
}

:deep(.el-dialog__header) {
  padding: 20px 24px 10px;
  border-bottom: 1px solid #eef2f7;
}

:deep(.el-dialog__title) {
  font-size: 24px;
  font-weight: 600;
  color: #17325f;
}

:deep(.el-dialog__body) {
  padding: 20px 24px 24px;
  background: #f8fafc;
}

:deep(.el-input__inner),
:deep(.el-textarea__inner) {
  border-radius: 10px;
}

@media (max-width: 1280px) {
  .work-order-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .work-order-page {
    width: calc(100% + 32px);
    margin: -16px;
    padding: 0 16px 24px;
  }

  .work-order-toolbar,
  .work-order-composer__header,
  .work-order-composer__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .work-order-composer__case {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .work-order-toolbar__status,
  .work-order-detail__images {
    width: 100%;
  }

  .work-order-detail__meta {
    grid-template-columns: 1fr;
  }

  .work-order-detail__images {
    grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  }
}
</style>
