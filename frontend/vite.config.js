import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    hmr: { port: 0 },  // 端口0=禁用HMR服务器，避免后台自动刷新页面
    allowedHosts: ['ov.nefu.edu.cn', '.nefu.edu.cn'],
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
