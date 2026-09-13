import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      // 开发环境同源代理到本地后端；生产用 VITE_API_BASE_URL 指定。
      '/api': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
