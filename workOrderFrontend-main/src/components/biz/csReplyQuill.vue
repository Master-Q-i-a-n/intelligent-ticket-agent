<template>
  <div class="cs-reply-editor" :class="{ 'is-disabled': disabled }">
    <div class="cs-reply-editor__toolbar">
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyCommand('bold')">
        B
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyCommand('italic')">
        I
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyCommand('underline')">
        U
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyCommand('insertOrderedList')">
        有序
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyCommand('insertUnorderedList')">
        无序
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="applyLink">
        链接
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="clearEditor">
        清除
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="triggerImageSelect">
        图片
      </button>
      <button type="button" class="cs-reply-editor__btn" :disabled="disabled" @mousedown.prevent @click="triggerAttachmentSelect">
        附件
      </button>
    </div>

    <div
      ref="editorRef"
      class="cs-reply-editor__content"
      :contenteditable="!disabled"
      :data-placeholder="placeholder"
      spellcheck="false"
      @input="handleInput"
      @focus="handleFocus"
      @blur="handleBlur"
      @click="handleEditorClick"
      @keydown="handleKeydown"
      @paste="handlePaste"
      @mouseup="captureSelection"
      @keyup="captureSelection"
    ></div>

    <input
      ref="imageInputRef"
      type="file"
      accept="image/*"
      class="cs-reply-editor__input"
      @change="handleImageSelect"
    />
    <input
      ref="attachmentInputRef"
      type="file"
      accept=".pdf,.xls,.xlsx,.doc,.docx"
      class="cs-reply-editor__input"
      @change="handleAttachmentSelect"
    />

    <div class="cs-reply-editor__footer">
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { uploadFile } from '../../api/file'

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, char => {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }
    return map[char]
  })
}

function normalizeHtml(html) {
  const value = String(html || '').trim()
  if (!value || value === '<p><br></p>' || value === '<div><br></div>') {
    return ''
  }
  return value
}

function getTextOnlyLength(root) {
  if (!root) {
    return 0
  }

  const clone = root.cloneNode(true)
  clone.querySelectorAll('img, .cs-reply-attachment, .ql-attachment').forEach(node => node.remove())
  return Math.max(0, (clone.innerText || '').replace(/\n/g, '').length)
}

function getUploadField(uploadData, keys = []) {
  if (typeof uploadData === 'string') {
    return uploadData
  }
  if (!uploadData || typeof uploadData !== 'object') {
    return ''
  }
  for (const key of keys) {
    if (uploadData[key]) {
      return uploadData[key]
    }
  }
  return ''
}

function createAttachmentHtml(value) {
  const fileUrl = value.url || ''
  const fileName = value.name || '附件'
  return `<span class="cs-reply-attachment" contenteditable="false" style="display:inline-flex;align-items:center;gap:0;padding:3px 8px;border-radius:999px;background:#eaf2ff;color:#2f6fe4;max-width:100%;vertical-align:middle;font-size:12px;line-height:1.4;"><a class="cs-reply-attachment__name" target="_blank" rel="noopener noreferrer" href="${escapeHtml(fileUrl)}" style="color:inherit;text-decoration:none;word-break:break-all;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(fileName)}</a></span>`
}

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '请输入回复内容...'
  },
  disabled: {
    type: Boolean,
    default: false
  },
  maxLength: {
    type: Number,
    default: 500
  }
})

const emit = defineEmits(['update:modelValue', 'state-change'])

const editorRef = ref(null)
const imageInputRef = ref(null)
const attachmentInputRef = ref(null)
const focused = ref(false)
const isSyncing = ref(false)
const selectionRange = ref(null)

function emitState() {
  const html = normalizeHtml(editorRef.value?.innerHTML || props.modelValue)
  const textLength = getTextOnlyLength(editorRef.value)
  const hasContent = Boolean(html) && /[^\s]/.test(html.replace(/<[^>]+>/g, '')) || /<img\b|cs-reply-attachment/.test(html)
  emit('state-change', { html, textLength, hasContent })
}

function syncFromModel(value) {
  if (!editorRef.value || isSyncing.value) {
    return
  }
  const normalized = normalizeHtml(value)
  const current = normalizeHtml(editorRef.value.innerHTML)
  if (normalized === current) {
    return
  }
  isSyncing.value = true
  editorRef.value.innerHTML = normalized
  isSyncing.value = false
  emitState()
}

function saveSelection() {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) {
    return
  }
  const range = selection.getRangeAt(0)
  if (!editorRef.value || !editorRef.value.contains(range.commonAncestorContainer)) {
    return
  }
  selectionRange.value = range.cloneRange()
}

function restoreSelection() {
  if (!selectionRange.value || !editorRef.value) {
    return null
  }
  const selection = window.getSelection()
  if (!selection) {
    return null
  }
  selection.removeAllRanges()
  selection.addRange(selectionRange.value)
  return selectionRange.value
}

function getFallbackRange() {
  if (selectionRange.value) {
    return selectionRange.value
  }
  if (!editorRef.value) {
    return null
  }
  const range = document.createRange()
  range.selectNodeContents(editorRef.value)
  range.collapse(false)
  return range
}

function insertHtmlAtSelection(html) {
  if (!editorRef.value) {
    return
  }
  editorRef.value.focus()
  const range = restoreSelection() || getFallbackRange()
  if (!range) {
    return
  }
  const selection = window.getSelection()
  if (!selection) {
    return
  }
  range.deleteContents()
  const wrapper = document.createElement('div')
  wrapper.innerHTML = html
  const fragment = document.createDocumentFragment()
  while (wrapper.firstChild) {
    fragment.appendChild(wrapper.firstChild)
  }
  const lastNode = fragment.lastChild
  range.insertNode(fragment)

  if (lastNode) {
    range.setStartAfter(lastNode)
    range.collapse(true)
    selection.removeAllRanges()
    selection.addRange(range)
    selectionRange.value = range.cloneRange()
  }
}

function appendHtmlAtEnd(html) {
  if (!editorRef.value) {
    return
  }
  const current = normalizeHtml(editorRef.value.innerHTML)
  const next = current ? `${current}${html}` : html
  isSyncing.value = true
  editorRef.value.innerHTML = next
  isSyncing.value = false
  selectionRange.value = null
  emit('update:modelValue', normalizeHtml(editorRef.value.innerHTML))
  emitState()
}

function updateFromEditor() {
  if (!editorRef.value || isSyncing.value) {
    return
  }
  const html = normalizeHtml(editorRef.value.innerHTML)
  if (!html) {
    editorRef.value.innerHTML = ''
  }
  emit('update:modelValue', html)
  emitState()
}

function applyCommand(command) {
  if (props.disabled) {
    return
  }
  editorRef.value?.focus()
  saveSelection()
  document.execCommand(command, false)
  updateFromEditor()
}

function applyLink() {
  if (props.disabled) {
    return
  }
  const url = window.prompt('请输入链接地址')
  if (!url) {
    return
  }
  editorRef.value?.focus()
  saveSelection()
  document.execCommand('createLink', false, url)
  updateFromEditor()
}

function clearEditor() {
  if (props.disabled || !editorRef.value) {
    return
  }
  isSyncing.value = true
  editorRef.value.innerHTML = ''
  isSyncing.value = false
  selectionRange.value = null
  updateFromEditor()
}

function openPreview(url) {
  if (!url) {
    return
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function handleFocus() {
  focused.value = true
}

function handleBlur() {
  focused.value = false
  saveSelection()
}

function handleKeydown() {
  saveSelection()
}

function handlePaste(event) {
  saveSelection()
  if (props.disabled) {
    event.preventDefault()
  }
}

function handleInput() {
  updateFromEditor()
}

function handleEditorClick(event) {
  const target = event.target
  if (target && target.tagName === 'IMG') {
    openPreview(target.currentSrc || target.src)
  }
}

function captureSelection() {
  saveSelection()
}

function triggerImageSelect() {
  if (!props.disabled) {
    saveSelection()
    imageInputRef.value?.click()
  }
}

function triggerAttachmentSelect() {
  if (!props.disabled) {
    saveSelection()
    attachmentInputRef.value?.click()
  }
}

async function insertImage(file) {
  const result = await uploadFile(file, 'image')
  const url = getUploadField(result?.data, ['imgUrl', 'url', 'fileUrl'])
  if (!url) {
    throw new Error('图片地址无效')
  }

  const html = `<p><img src="${escapeHtml(url)}" alt="${escapeHtml(file.name)}" /></p>`
  if (selectionRange.value && editorRef.value && editorRef.value.textContent?.trim()) {
    insertHtmlAtSelection(html)
  } else {
    appendHtmlAtEnd(html)
  }
  updateFromEditor()
}

async function insertAttachment(file) {
  const result = await uploadFile(file, 'file')
  const data = result?.data || {}
  const url = getUploadField(data, ['url', 'fileUrl', 'imgUrl'])
  if (!url) {
    throw new Error('附件地址无效')
  }

  const html = createAttachmentHtml({
    name: data.name || file.name,
    url
  })
  if (selectionRange.value && editorRef.value && editorRef.value.textContent?.trim()) {
    insertHtmlAtSelection(html)
  } else {
    appendHtmlAtEnd(html)
  }
  updateFromEditor()
}

async function handleImageSelect(event) {
  const file = event.target.files && event.target.files[0]
  event.target.value = ''
  if (!file) {
    return
  }

  try {
    await insertImage(file)
  } catch (error) {
    console.error(error)
  }
}

async function handleAttachmentSelect(event) {
  const file = event.target.files && event.target.files[0]
  event.target.value = ''
  if (!file) {
    return
  }

  try {
    await insertAttachment(file)
  } catch (error) {
    console.error(error)
  }
}

watch(
  () => props.modelValue,
  value => syncFromModel(value)
)

watch(
  () => props.disabled,
  value => {
    if (editorRef.value) {
      editorRef.value.setAttribute('contenteditable', String(!value))
    }
  }
)

onMounted(async () => {
  await nextTick()
  if (editorRef.value) {
    editorRef.value.innerHTML = normalizeHtml(props.modelValue)
    editorRef.value.setAttribute('contenteditable', String(!props.disabled))
  }
  document.addEventListener('selectionchange', saveSelection)
  emitState()
})

onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', saveSelection)
})

const textLength = computed(() => {
  if (!editorRef.value) {
    return 0
  }
  return getTextOnlyLength(editorRef.value)
})
</script>

<style scoped>
.cs-reply-editor {
  display: grid;
  gap: 0;
  width: 100%;
}

.cs-reply-editor__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #dbe6f7;
  border-bottom: 0;
  border-radius: 14px 14px 0 0;
  background: #f8fbff;
}

.cs-reply-editor__btn {
  border: 1px solid #c8d7ea;
  border-radius: 8px;
  background: #fff;
  color: #35517a;
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  cursor: pointer;
}

.cs-reply-editor__btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.cs-reply-editor__content {
  min-height: 140px;
  padding: 14px 16px;
  border: 1px solid #dbe6f7;
  border-radius: 0 0 14px 14px;
  background: #fff;
  font-size: 14px;
  line-height: 1.8;
  color: #44536d;
  white-space: pre-wrap;
  word-break: break-word;
  outline: none;
}

.cs-reply-editor__content:empty::before {
  content: attr(data-placeholder);
  color: #a7b3c5;
}

.cs-reply-editor__input {
  display: none;
}

.cs-reply-editor__content :deep(img) {
  max-width: 100%;
  height: auto;
  display: inline-block;
  border-radius: 10px;
  cursor: zoom-in;
}

.cs-reply-editor__content :deep(.cs-reply-attachment) {
  display: inline-flex;
  align-items: center;
  gap: 0;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf2ff;
  color: #2f6fe4;
  max-width: 100%;
  vertical-align: middle;
  font-size: 12px;
  line-height: 1.4;
}

.cs-reply-editor__content :deep(.cs-reply-attachment__name) {
  color: inherit;
  text-decoration: none;
  word-break: break-all;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cs-reply-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: #7a8799;
  padding: 10px 0;
}
</style>
