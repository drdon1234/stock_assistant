<script setup>
import { computed, h, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  NAutoComplete, NButton, NConfigProvider, NDialogProvider, NDrawer, NDrawerContent, NDropdown, NLayout, NLayoutSider,
  NMenu, NMessageProvider, NTooltip, darkTheme, dateZhCN, zhCN,
} from 'naive-ui'
import Icon from './components/Icon.vue'
import Login from './views/Login.vue'
import { api } from './api'
import { cycleTheme, isDark, isMobile, loadAttention, loadMeta, loadSession, logout, state } from './store'
import { KIND_LABELS } from './strategy'

const route = useRoute()
const router = useRouter()
const drawer = ref(false)
const collapsed = ref(false)

const GROUP_ICONS = { 行情: 'grid', 资金: 'coins', 事件: 'bell', 分析: 'chart' }
const icon = (name) => () => h(Icon, { name })

// 买入、卖出策略各为一个一级入口，每个策略为二级入口
const strategyGroup = (kind) => ({
  label: KIND_LABELS[kind],
  key: `strategies:${kind}`,
  icon: icon(kind),
  children: [
    { label: '策略总览', key: `/strategies/${kind}` },
    ...(state.meta?.strategies || []).filter((s) => s.kind === kind).map((s) => ({ label: s.name, key: `/strategy/${s.key}` })),
  ],
})

const menuOptions = computed(() => [
  { label: '市场概览', key: '/', icon: icon('home') },
  ...(state.meta?.menu || []).map((g) => ({
    label: g.group,
    key: g.group,
    icon: icon(GROUP_ICONS[g.group] || 'grid'),
    children: g.tables.map((t) => ({ label: t.label, key: `/table/${t.name}` })),
  })),
  strategyGroup('buy'),
  strategyGroup('sell'),
  { label: '聚宽策略回测', key: '/quant', icon: icon('target') },
  { label: '我的关注', key: '/attention', icon: icon('star') },
  { label: '学习中心', key: '/learn', icon: icon('book') },
])

const activeKey = computed(() => route.path)
const expandedKeys = ref([])
// 进入某个二级页面时展开它所在的分组
watch(() => [route.path, state.meta], () => {
  const parent = menuOptions.value.find((o) => o.children?.some((c) => c.key === route.path))
  if (parent && !expandedKeys.value.includes(parent.key)) expandedKeys.value = [...expandedKeys.value, parent.key]
}, { immediate: true })

function go(key) {
  router.push(key)
  drawer.value = false
}

const keyword = ref('')
const options = ref([])
let searchTimer
watch(keyword, (q) => {
  clearTimeout(searchTimer)
  if (!q?.trim()) {
    options.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    try {
      const { items } = await api.search(q)
      options.value = items.map((i) => ({ label: `${i.code}  ${i.name}  ·  ${i.kind}`, value: i.code }))
    } catch {
      options.value = []
    }
  }, 200)
})

function onSelect(code) {
  keyword.value = ''
  router.push(`/stock/${code}`)
}

const themeIcon = computed(() => ({ auto: 'auto', light: 'sun', dark: 'moon' })[state.themeMode])
const themeLabel = computed(() => ({ auto: '跟随系统', light: '浅色', dark: '深色' })[state.themeMode])
const themeOverrides = computed(() => ({
  common: {
    primaryColor: isDark.value ? '#4f8cff' : '#2563eb',
    primaryColorHover: isDark.value ? '#6b9fff' : '#3b74f0',
    primaryColorPressed: isDark.value ? '#3a78ea' : '#1d4fd0',
    borderRadius: '8px',
    fontFamily: 'inherit',
  },
}))

const userOptions = computed(() => [
  { key: 'who', type: 'render', render: () => h('div', { class: 'user-who' }, [
    h('b', state.user?.username), h('span', { class: 'muted' }, state.user?.admin ? '管理员' : '普通账号'),
  ]) },
  { type: 'divider', key: 'd1' },
  { label: state.user?.admin ? '账号设置与管理' : '账号设置', key: 'account', icon: icon('user') },
  { label: '退出登录', key: 'logout', icon: icon('logout') },
])

async function onUserMenu(key) {
  if (key === 'account') go('/account')
  else if (key === 'logout') await logout()
}

// 登录后（含页面刷新时凭证仍有效）加载菜单与关注列表
watch(() => state.user?.username, (name) => {
  if (!name) return
  loadMeta()
  loadAttention().catch(() => {})
})

onMounted(() => {
  loadSession().catch(() => {})
})
</script>

<template>
  <NConfigProvider :theme="isDark ? darkTheme : null" :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <div v-if="!state.authChecked" class="shell" />
        <Login v-else-if="!state.user" />
        <NLayout v-else class="shell" :has-sider="!isMobile">
          <NLayoutSider v-if="!isMobile" bordered collapse-mode="width" :collapsed-width="64" :width="220"
                        :collapsed="collapsed" show-trigger="bar" class="sider"
                        @collapse="collapsed = true" @expand="collapsed = false">
            <RouterLink to="/" class="brand">
              <img src="/favicon.svg" alt="" width="28" height="28" />
              <span v-show="!collapsed">InStock</span>
            </RouterLink>
            <NMenu :options="menuOptions" :value="activeKey" :collapsed="collapsed" :collapsed-width="64"
                   :collapsed-icon-size="20" v-model:expanded-keys="expandedKeys" @update:value="go" />
          </NLayoutSider>
          <div class="main">
            <header class="header">
              <NButton v-if="isMobile" quaternary circle @click="drawer = true" aria-label="菜单">
                <Icon name="menu" />
              </NButton>
              <RouterLink v-if="isMobile" to="/" class="brand compact">InStock</RouterLink>
              <NAutoComplete v-model:value="keyword" :options="options" placeholder="搜索代码 / 名称"
                             clearable class="search" :get-show="() => true" @select="onSelect">
                <template #prefix><Icon name="search" :size="16" /></template>
              </NAutoComplete>
              <NTooltip>
                <template #trigger>
                  <NButton quaternary circle aria-label="学习中心" @click="go('/learn')">
                    <Icon name="book" />
                  </NButton>
                </template>
                学习中心：术语、指标、形态与策略说明
              </NTooltip>
              <NTooltip>
                <template #trigger>
                  <NButton quaternary circle @click="cycleTheme" :aria-label="`主题：${themeLabel}`">
                    <Icon :name="themeIcon" />
                  </NButton>
                </template>
                主题：{{ themeLabel }}
              </NTooltip>
              <NDropdown trigger="click" :options="userOptions" placement="bottom-end" @select="onUserMenu">
                <NButton quaternary circle :aria-label="`账号：${state.user.username}`">
                  <Icon name="user" />
                </NButton>
              </NDropdown>
            </header>
            <main class="content">
              <RouterView :key="route.path" />
            </main>
          </div>
        </NLayout>
        <NDrawer v-if="state.user" v-model:show="drawer" placement="left" :width="260">
          <NDrawerContent body-content-style="padding: 8px 0">
            <template #header>
              <div class="brand drawer-brand"><img src="/favicon.svg" alt="" width="26" height="26" /> InStock</div>
            </template>
            <NMenu :options="menuOptions" :value="activeKey" v-model:expanded-keys="expandedKeys" @update:value="go" />
          </NDrawerContent>
        </NDrawer>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.shell { height: 100vh; height: 100dvh; background: var(--bg); }
.sider { background: var(--surface); }
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 18px;
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap;
}
.brand.compact { padding: 0; height: auto; }
.drawer-brand { padding: 0; height: auto; }
.main { display: flex; flex-direction: column; flex: 1; min-width: 0; height: 100%; }
.header {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 56px;
  flex: none;
  padding: 0 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.search { max-width: 360px; margin-left: auto; }
.content { flex: 1; min-height: 0; overflow: auto; }
:global(.user-who) { display: flex; flex-direction: column; gap: 2px; padding: 6px 14px 8px; min-width: 160px; }
:global(.user-who span) { font-size: 12px; }
@media (max-width: 767px) {
  .header { padding: 0 8px; gap: 4px; }
  .search { max-width: none; flex: 1; }
}
</style>
