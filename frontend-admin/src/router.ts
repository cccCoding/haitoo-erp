import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

// 页面内容和共享数据由 App.vue 管理，路由负责地址和浏览器历史。
const RouteOutlet = { template: '<span aria-hidden="true" />' }

export const adminRoutes: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'overview' } },
  { path: '/overview', name: 'overview', component: RouteOutlet },
  { path: '/conpanies', name: 'companies', component: RouteOutlet },
  { path: '/companies', redirect: { name: 'companies' } },
  { path: '/models', name: 'models', component: RouteOutlet },
  { path: '/:pathMatch(.*)*', redirect: { name: 'overview' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes: adminRoutes,
})
