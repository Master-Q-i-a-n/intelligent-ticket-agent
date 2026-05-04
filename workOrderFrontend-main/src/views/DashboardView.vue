<template>
  <section class="hero-card">
    <div>
      <p class="eyebrow">本地优先 / 接口驱动</p>
      <h1>工单系统</h1>
      <p class="lead">
        用户端提交反馈，管理端处理工单，所有列表、详情、回复和状态都直接来自后端真实数据。
      </p>
    </div>
  </section>

  <section class="grid-cards">
    <article class="mini-card">
      <h3>前端</h3>
      <p>Vue 3 + Vite + Element Plus，页面直接联通后端接口，没有本地兜底数据。</p>
    </article>
    <article class="mini-card">
      <h3>后端</h3>
      <p>Spring Boot 3 + Java 17，工单数据保存在数据库中，前后端共享同一条记录。</p>
    </article>
    <article class="mini-card">
      <h3>联调</h3>
      <p>通过 /api 代理对接本地后端，用户和管理员看到的是同一套中文真实数据。</p>
    </article>
  </section>
</template>
