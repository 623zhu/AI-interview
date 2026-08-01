/// <reference types="vite/client" />

/** 暴露给浏览器的前端环境变量，名称必须以 VITE_ 开头。 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
