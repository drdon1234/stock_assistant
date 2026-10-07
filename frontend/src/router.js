import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '市场概览' } },
    { path: '/table/:name', name: 'table', component: () => import('./views/TableView.vue') },
    { path: '/strategy', name: 'strategy', component: () => import('./views/Strategy.vue'), meta: { title: '策略选股' } },
    { path: '/stock/:code', name: 'stock', component: () => import('./views/StockView.vue') },
    { path: '/attention', name: 'attention', component: () => import('./views/Attention.vue'), meta: { title: '我的关注' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
