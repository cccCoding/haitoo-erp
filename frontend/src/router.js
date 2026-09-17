import { createRouter, createWebHistory } from 'vue-router';
// App.vue owns the shared authenticated shell and its in-memory workspace state.
// These records make every primary workspace area addressable without turning
// navigation into a full-page reload.
const RouteOutlet = { template: '<span aria-hidden="true" />' };
export const workspaceRoutes = [
    { path: '/', redirect: { name: 'dashboard' } },
    { path: '/dashboard', name: 'dashboard', component: RouteOutlet },
    { path: '/templates', name: 'templates', component: RouteOutlet },
    { path: '/creative', name: 'pod', component: RouteOutlet },
    { path: '/tasks', name: 'tasks', component: RouteOutlet },
    { path: '/materials', name: 'materials', component: RouteOutlet },
    { path: '/drafts', name: 'drafts', component: RouteOutlet },
    { path: '/settings/members', name: 'members', component: RouteOutlet, meta: { requiresCompanyAdmin: true } },
    { path: '/settings/shops', name: 'shops', component: RouteOutlet, meta: { requiresCompanyAdmin: true } },
    { path: '/settings/tiktok-catalogs', name: 'tiktok-catalogs', component: RouteOutlet, meta: { requiresCompanyAdmin: true } },
    { path: '/:pathMatch(.*)*', redirect: { name: 'dashboard' } },
];
export const router = createRouter({
    history: createWebHistory(),
    routes: workspaceRoutes,
});
