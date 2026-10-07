import { computed, ref, watch } from 'vue'

// 数据表显示哪些列：只保存与默认值不同的列，表结构新增列时自动使用默认设置
const key = (table) => `instock-cols:${table}`

function read(table) {
  try {
    return JSON.parse(localStorage.getItem(key(table))) || {}
  } catch {
    return {}
  }
}

/** groups 为 buildGroups 的结果（ref/computed）。 */
export function useColumnVisibility(table, groups) {
  const overrides = ref(read(table))
  const all = computed(() => groups.value.flatMap((g) => g.cols))
  const visible = computed(() => new Set(all.value.filter((c) => overrides.value[c.name] ?? c.defaultOn).map((c) => c.name)))
  const isDefault = computed(() => all.value.every((c) => visible.value.has(c.name) === c.defaultOn))

  watch(overrides, (value) => {
    try {
      if (Object.keys(value).length) localStorage.setItem(key(table), JSON.stringify(value))
      else localStorage.removeItem(key(table))
    } catch {
      // 无法存储时只在本次会话生效
    }
  })

  function setVisible(names) {
    const on = new Set(names)
    const next = {}
    for (const c of all.value) if (on.has(c.name) !== c.defaultOn) next[c.name] = on.has(c.name)
    overrides.value = next
  }

  return {
    visible,
    isDefault,
    total: computed(() => all.value.length),
    setVisible,
    reset: () => { overrides.value = {} },
    showAll: () => setVisible(all.value.map((c) => c.name)),
  }
}
