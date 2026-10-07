import { reactive } from 'vue'

// 记录用户收起过的页面说明，保存在本机浏览器
const KEY = 'instock-guide-closed'

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    return {}
  }
}

const closed = reactive(read())

export const guideOpen = (id) => !closed[id]

export function toggleGuide(id) {
  if (closed[id]) delete closed[id]
  else closed[id] = true
  try {
    localStorage.setItem(KEY, JSON.stringify(closed))
  } catch {
    // 隐私模式等无法存储时只在本次会话生效
  }
}
