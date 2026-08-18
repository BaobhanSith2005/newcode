import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  server: {
    port: 5173,
    proxy: {
      // 同款代码见 AIRoomBuilder/frontend/vite.config.ts 第15行
      // 前端代码里写 /api/xxx，开发服务器自动转发到后端 :8000，
      // 这样前端永远不用关心后端真实地址
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
})
