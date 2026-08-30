import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // Cloudflare Tunnel 以此 Host 转发到 Vite 开发服务器。
    allowedHosts: ['erp.haitoro.com'],
  },
})
