import { computed, reactive, watchEffect } from 'vue'
import { api, setUnauthorizedHandler } from './api'

const THEME_KEY = 'instock-theme'
const media = window.matchMedia('(prefers-color-scheme: dark)')

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || 'auto'
  } catch {
    return 'auto'
  }
}

export const state = reactive({
  meta: null,
  themeMode: storedTheme(), // auto | light | dark
  systemDark: media.matches,
  attention: new Set(),
  width: window.innerWidth,
  user: null, // { username, admin }
  authChecked: false,
  setup: false, // 服务器还没有任何账号
  sessionDays: null,
})

media.addEventListener('change', (e) => { state.systemDark = e.matches })
window.addEventListener('resize', () => { state.width = window.innerWidth })

export const isDark = computed(() => (state.themeMode === 'auto' ? state.systemDark : state.themeMode === 'dark'))
export const isMobile = computed(() => state.width < 768)

watchEffect(() => {
  document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
  try {
    localStorage.setItem(THEME_KEY, state.themeMode)
  } catch {
    // 隐私模式等无法存储时忽略
  }
})

export function cycleTheme() {
  const order = ['auto', 'light', 'dark']
  state.themeMode = order[(order.indexOf(state.themeMode) + 1) % order.length]
}

export async function loadMeta() {
  if (!state.meta) state.meta = await api.meta()
  return state.meta
}

function signedOut() {
  state.user = null
  state.attention = new Set()
}

setUnauthorizedHandler(signedOut)

export async function loadSession() {
  try {
    const { user, setup, days } = await api.session()
    Object.assign(state, { user, setup, sessionDays: days })
  } finally {
    state.authChecked = true
  }
}

export async function login(username, password) {
  state.user = (await api.login(username, password)).user
}

export async function logout() {
  await api.logout().catch(() => {})
  signedOut()
}

export async function loadAttention() {
  const { codes } = await api.attention()
  state.attention = new Set(codes)
}

export async function toggleAttention(code) {
  if (state.attention.has(code)) {
    await api.removeAttention(code)
    state.attention.delete(code)
  } else {
    await api.addAttention(code)
    state.attention.add(code)
  }
  state.attention = new Set(state.attention)
}
