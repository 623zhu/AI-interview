import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        // Disable buffering for SSE streaming
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.url?.includes('/chat/stream')) {
              proxyReq.setHeader('Connection', 'keep-alive')
              proxyReq.setHeader('Cache-Control', 'no-cache')
            }
          })
          proxy.on('proxyRes', (proxyRes, req) => {
            if (req.url?.includes('/chat/stream')) {
              // Prevent proxy from buffering SSE responses
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
})
