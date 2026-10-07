import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('./views/Overview.vue'), meta: { title: '市场概览' } },
    { path: '/table/cn_stock_pattern', name: 'pattern', component: () => import('./views/PatternView.vue') },
    { path: '/table/:name', name: 'table', component: () => import('./views/TableView.vue') },
    { path: '/strategies/:kind(buy|sell)', name: 'strategies', component: () => import('./views/StrategyList.vue') },
    { path: '/strategy/:key', name: 'strategy', component: () => import('./views/StrategyDetail.vue') },
    // 旧地址 /strategy?key=xxx 仍可访问
    { path: '/strategy', redirect: (to) => ({ path: to.query.key ? `/strategy/${to.query.key}` : '/strategies/buy', query: {} }) },
    { path: '/stock/:code', name: 'stock', component: () => import('./views/StockView.vue') },
    { path: '/quant', name: 'quant', component: () => import('./views/Quant.vue'), meta: { title: '聚宽策略回测' } },
    { path: '/attention', name: 'attention', component: () => import('./views/Attention.vue'), meta: { title: '我的关注' } },
    { path: '/account', name: 'account', component: () => import('./views/Account.vue'), meta: { title: '账号设置' } },
    { path: '/learn', name: 'learn', component: () => import('./views/Learn.vue'), meta: { title: '学习中心' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
