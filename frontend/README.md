# Frontend

前端采用单一 npm 工程和两个 Vue 入口，共用依赖但保持运行时隔离。

```text
frontend/
|-- index.html       # 候选人端 HTML 入口
|-- admin.html       # 管理端 HTML 入口
|-- user/src/        # 候选人端 Vue 应用
|-- admin/src/       # 管理端 Vue 应用
|-- shared/src/      # 两端共享的类型、认证和请求基础设施
|-- package.json     # 唯一依赖清单
`-- vite.config.ts   # 双入口构建和开发代理
```

## 开发地址

- 候选人端：`http://127.0.0.1:5173/`
- 管理端：`http://127.0.0.1:5173/admin.html`

## 常用命令

```bash
npm install
npm run dev
npm run build
```

## 边界规则

1. `user` 不得导入 `admin` 中的文件。
2. `admin` 不得导入 `user` 中的文件。
3. 两端只通过 `shared` 复用跨端代码。
4. 页面、路由和业务 Store 必须留在各自应用内。
5. 管理权限始终由后端校验，前端入口隔离不属于安全边界。
