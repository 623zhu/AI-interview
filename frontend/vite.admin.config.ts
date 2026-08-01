import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'admin-entry',
      transformIndexHtml(html) {
        return html.replace('/src/main.ts', '/src/main.admin.ts')
      },
    },
  ],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.url?.includes('/chat/stream')) {
              proxyReq.setHeader('Connection', 'keep-alive')
              proxyReq.setHeader('Cache-Control', 'no-cache')
            }
          })
          proxy.on('proxyRes', (proxyRes, req) => {
            if (req.url?.includes('/chat/stream')) {
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
      '/uploads': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        admin: resolve(import.meta.dirname, 'admin.html'),
      },
    },
  },
})
