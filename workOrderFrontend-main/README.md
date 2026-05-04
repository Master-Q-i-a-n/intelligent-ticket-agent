# Work Order Frontend

这是工单系统的前端项目，基于 Vue 3 + Vite。

后端仓库在这里：[Work Order Backend](https://github.com/mxnican/workOrderBackend)

## 新电脑第一次使用

1. 安装 Node.js 18 或更高版本。
2. `git clone` 本仓库到本地。
3. 进入项目目录后执行：

```powershell
npm install
```

4. 先启动后端服务，再启动前端开发服务器。
5. 启动前端：

```powershell
npm run dev
```

6. 浏览器打开 `http://127.0.0.1:5173`。

## 一页式启动顺序

如果你想最快跑起来，按这个顺序就行：

1. 先启动 MySQL，并创建 `work_order` 数据库。
2. 启动后端项目。
3. 启动前端项目。
4. 浏览器打开前端地址并登录。

## 开发时怎么联调

- 前端开发服务器会把 `/api` 转发到 `http://127.0.0.1:8080`。
- 所以前端本地开发时，默认只需要保证后端跑在 8080 端口即可。
- 如果后端端口改了，需要同步修改 `vite.config.js` 里的代理地址。

## 演示账号

首次启动后端后，系统会自动生成两组演示账号：

- 用户：`user / user123`
- 管理员：`admin / admin123`

登录后可以在个人中心里修改昵称、头像和密码。

## 前端会保存什么

- 前端不会保存业务数据。
- 登录态会保存在浏览器 `localStorage` 中，键名是 `workorder.session`。
- 退出登录会清理这份浏览器本地会话。

## 常用命令

```powershell
npm install
npm run dev
npm run build
```

`npm run build` 用于打包前端静态资源。
