import { computed } from 'vue'
import { isDark } from './store'

// 画布图表无法使用 CSS 变量，这里与 style.css 中的主题色保持一致
export const colors = computed(() => (isDark.value
  ? { up: '#f25d5d', down: '#2fbf71', flat: '#6b7280', text: '#e7e9ee', muted: '#9aa1ad', grid: '#2a2c33', primary: '#4f8cff' }
  : { up: '#e03131', down: '#12a150', flat: '#9ca3af', text: '#15171a', muted: '#6b7280', grid: '#eceef1', primary: '#2563eb' }))

export const SERIES_COLORS = ['#f59f00', '#7950f2', '#1c7ed6', '#e64980', '#0ca678', '#868e96']
