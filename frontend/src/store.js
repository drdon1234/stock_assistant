import { computed, reactive, watchEffect } from 'vue'
import { api } from './api'

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
