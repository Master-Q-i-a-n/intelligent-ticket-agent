# Work Order Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the full Chinese work order and feedback business flow from the source admin frontend into `workOrderFrontend`, and make `workOrderBackend` serve the same real persisted ticket data with no mock fallback.

**Architecture:** Keep the current Vue 3 + Element Plus shell, but replace the simplified views with feature-complete feedback/work-order pages backed by shared ticket helpers and a small rich-text reply input. On the backend, keep the shared `wo_feedback` / `wo_feedback_reply` persistence model, seed it with Chinese records, and expose the existing list/detail/create/reply/status endpoints as the single source of truth.

**Tech Stack:** Vue 3, Element Plus, Vite, Axios, Spring Boot 3, Spring JDBC, JUnit 5

---

### Task 1: Add shared ticket UI helpers

**Files:**
- Create: `D:/wly/workOrderFrontend/src/utils/ticket.js`
- Create: `D:/wly/workOrderFrontend/src/components/biz/csReplyQuill.vue`

- [ ] **Step 1: Define the helper API**

```js
export function mapTicketStatus(value) {}
export function formatTicketTime(value) {}
export function normalizeAttachmentList(list) {}
export function normalizeImageList(value) {}
export function buildReplyHtml(content) {}
```

- [ ] **Step 2: Implement the helper and reply input**

```vue
<template>
  <div class="reply-quill">
    <el-input v-model="content" type="textarea" :rows="6" :maxlength="maxLength" :placeholder="placeholder" />
  </div>
</template>
```

- [ ] **Step 3: Verify the component emits `v-model` and `state-change`**

Run: `npm run build`
Expected: build succeeds without missing component errors.

### Task 2: Migrate the user feedback page

**Files:**
- Modify: `D:/wly/workOrderFrontend/src/views/FeedbackView.vue`
- Modify: `D:/wly/workOrderFrontend/src/api/feedback.js`

- [ ] **Step 1: Replace the simplified page with the full Chinese feedback UI**

```vue
<template>
  <!-- list, detail, attachments, reply composer, create dialog -->
</template>
```

- [ ] **Step 2: Wire the page directly to `/api/feedback/page`, `/api/feedback/{id}`, `/api/feedback`, `/api/feedback/{id}/reply`**

```js
const res = await pageFeedback({ keyword, status, pageNum, pageSize })
```

- [ ] **Step 3: Remove every mock import and every mock fallback**

Run: `npm run build`
Expected: no `*.mock.*` imports remain in the feedback page.

### Task 3: Migrate the admin work-order page

**Files:**
- Modify: `D:/wly/workOrderFrontend/src/views/WorkOrderView.vue`
- Modify: `D:/wly/workOrderFrontend/src/api/workOrder.js`

- [ ] **Step 1: Replace the simplified page with the full Chinese work-order management UI**

```vue
<template>
  <!-- stats, filters, table, detail dialog, status buttons, reply composer -->
</template>
```

- [ ] **Step 2: Wire list, status update, and admin reply to the backend APIs**

```js
const res = await pageWorkOrders({ keyword, status, pageNum, pageSize })
await updateWorkOrderStatus(id, { status, remark })
await replyWorkOrder(id, { content, author })
```

- [ ] **Step 3: Remove every mock import and every mock fallback**

Run: `npm run build`
Expected: no `*.mock.*` imports remain in the work-order page.

### Task 4: Localize the shell and landing/login screens

**Files:**
- Modify: `D:/wly/workOrderFrontend/src/App.vue`
- Modify: `D:/wly/workOrderFrontend/src/views/LoginView.vue`
- Modify: `D:/wly/workOrderFrontend/src/views/DashboardView.vue`
- Modify: `D:/wly/workOrderFrontend/src/styles/main.css`

- [ ] **Step 1: Switch the shell copy to Chinese role labels**
- [ ] **Step 2: Align the landing/login text with the Chinese ticket workflow**
- [ ] **Step 3: Keep the existing routing and auth behavior unchanged**

Run: `npm run build`
Expected: shell and landing screens still render after the page replacements.

### Task 5: Make the backend the single source of truth

**Files:**
- Modify: `D:/wly/workOrderBackend/src/main/java/com/wly/workorder/config/DatabaseSeeder.java`
- Modify: `D:/wly/workOrderBackend/src/main/java/com/wly/workorder/service/impl/JdbcTicketService.java`
- Modify: `D:/wly/workOrderBackend/src/main/java/com/wly/workorder/model/TicketModels.java`
- Modify: `D:/wly/workOrderBackend/src/test/java/com/wly/workorder/controller/AuthFlowTest.java`

- [ ] **Step 1: Seed Chinese feedback/work-order rows and replies**
- [ ] **Step 2: Ensure both roles read from the same persisted tables**
- [ ] **Step 3: Keep admin status changes and replies synchronized in the shared thread**
- [ ] **Step 4: Extend tests to verify Chinese seeded data and admin reply/status flows**

Run: `mvn test`
Expected: backend tests pass with Chinese seed data and shared-thread behavior.

### Task 6: Full verification

**Files:**
- Test: `D:/wly/workOrderFrontend/package.json`
- Test: `D:/wly/workOrderBackend/pom.xml`

- [ ] **Step 1: Build the frontend**

Run: `npm run build`
Expected: successful production build.

- [ ] **Step 2: Run backend tests**

Run: `mvn test`
Expected: all backend tests pass.

- [ ] **Step 3: Open the app and confirm both roles work with real data**

Expected: user can create and reply on `/feedback`; admin can manage and reply on `/work-order`; both views show the same Chinese persisted tickets.
