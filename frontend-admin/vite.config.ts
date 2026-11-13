import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  // 用户视角复用 ERP 组件；统一依赖到管理端，避免重复 Vue 实例。
  resolve: { dedupe: ['vue', 'vue-router', 'axios'] },
  server: {
    port: 5174,
    // Cloudflare Tunnel 以此 Host 转发到 Vite 开发服务器。
    allowedHosts: ['admin.haitoro.com'],
  },
})
