export const TICKET_STATUS_META = {
  PENDING: {
    label: '待处理',
    className: 'is-pending',
    iconName: 'Clock'
  },
  PROCESSING: {
    label: '处理中',
    className: 'is-processing',
    iconName: 'WarningFilled'
  },
  SOLVED: {
    label: '已解决',
    className: 'is-solved',
    iconName: 'CircleCheckFilled'
  },
  CLOSED: {
    label: '已关闭',
    className: 'is-closed',
    iconName: 'CircleCloseFilled'
  }
}

export const TICKET_STATUS_OPTIONS = [
  { label: '待处理', value: '待处理' },
  { label: '处理中', value: '处理中' },
  { label: '已解决', value: '已解决' },
  { label: '已关闭', value: '已关闭' }
]

export const TICKET_PRIORITY_META = {
  低: {
    label: '低',
    className: 'is-low'
  },
  中: {
    label: '中',
    className: 'is-medium'
  },
  高: {
    label: '高',
    className: 'is-high'
  },
  紧急: {
    label: '紧急',
    className: 'is-urgent'
  },
  unknown: {
    label: '未知',
    className: 'is-low'
  }
}

export const TICKET_PRIORITY_OPTIONS = [
  { label: '低', value: '低' },
  { label: '中', value: '中' },
  { label: '高', value: '高' },
  { label: '紧急', value: '紧急' },
  { label: '未知', value: '未知' }
]

export const TICKET_CATEGORY_OPTIONS = [
  { label: '技术故障', value: '技术故障' },
  { label: '产品咨询', value: '产品咨询' },
  { label: '功能需求', value: '功能需求' },
  { label: '投诉建议', value: '投诉建议' },
  { label: '账单问题', value: '账单问题' },
  { label: '其他', value: '其他' }
]

export function createUid(prefix) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`
}

export function getNowString(date = new Date()) {
  const pad = value => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate())
  ].join('-') + ` ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

export function formatTicketTime(value) {
  return value || '--'
}

export function getFileExtension(name) {
  const parts = String(name || '').split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

export function getAssetName(path) {
  const normalizedPath = String(path || '').split('?')[0]
  const segments = normalizedPath.split('/')
  return segments.pop() || normalizedPath || 'file'
}

export function resolveAssetUrl(path) {
  const normalizedPath = String(path || '').trim().split('?')[0]
  if (!normalizedPath) {
    return ''
  }
  if (/^(https?:)?\/\//i.test(normalizedPath) || normalizedPath.startsWith('data:') || normalizedPath.startsWith('blob:')) {
    return normalizedPath
  }
  if (normalizedPath.startsWith('/api/files/')) {
    return normalizedPath
  }
  if (normalizedPath.startsWith('api/files/')) {
    return `/${normalizedPath}`
  }
  return `/api/files/${normalizedPath.replace(/^\/+/, '')}`
}

export function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function buildReplyHtml(content) {
  const safeText = String(content || '').trim()
  if (!safeText) {
    return '<p><br></p>'
  }

  if (/<[a-z][\s\S]*>/i.test(safeText)) {
    return safeText
  }

  return safeText
    .split(/\n+/)
    .filter(Boolean)
    .map(item => `<p>${escapeHtml(item)}</p>`)
    .join('')
}

export function mapTicketStatus(value) {
  const normalized = String(value || '').trim().toUpperCase()
  const alias = {
    WAIT: 'PENDING',
    WAITING: 'PENDING',
    UNTREATED: 'PENDING',
    DEALING: 'PROCESSING',
    FINISHED: 'SOLVED',
    RESOLVED: 'SOLVED',
    FINISH: 'SOLVED',
    CLOSE: 'CLOSED'
  }
  return TICKET_STATUS_META[normalized] ? normalized : alias[normalized] || 'PENDING'
}

function normalizeAsset(item = {}, uidPrefix = 'asset') {
  const assetPath = item.serverPath || item.fileUrl || item.url || ''
  const resolvedUrl = resolveAssetUrl(assetPath)
  return {
    uid: item.uid || createUid(uidPrefix),
    name: item.name || getAssetName(assetPath),
    url: resolvedUrl,
    fileUrl: resolvedUrl,
    serverPath: assetPath,
    ext: item.ext || getFileExtension(item.name || assetPath)
  }
}

export function normalizeAttachmentList(list) {
  return (list || []).map(item => normalizeAsset(item, 'file'))
}

export function normalizeImageList(value) {
  const list = Array.isArray(value) ? value : String(value || '').split(',')
  return list
    .map((item, index) => {
      const assetPath = typeof item === 'string' ? item.trim() : item && (item.serverPath || item.fileUrl || item.url || '')
      if (!assetPath) {
        return null
      }
      const name = typeof item === 'object' && item ? item.name : getAssetName(assetPath) || `image_${index + 1}`
      return normalizeAsset({ ...item, name, url: assetPath, fileUrl: assetPath, serverPath: assetPath }, 'img')
    })
    .filter(Boolean)
}

export function serializeAssetList(list) {
  return (list || [])
    .map(item => item && (item.serverPath || item.fileUrl || item.url || ''))
    .filter(Boolean)
}

export function toStatusMeta(status) {
  return TICKET_STATUS_META[mapTicketStatus(status)] || TICKET_STATUS_META.PENDING
}

export function getReplyRoleLabel(role) {
  return String(role || '').toLowerCase() === 'service' ? '客服' : '用户'
}

export function toPriorityMeta(priority) {
  return TICKET_PRIORITY_META[priority] || TICKET_PRIORITY_META.UNKNOWN
}
