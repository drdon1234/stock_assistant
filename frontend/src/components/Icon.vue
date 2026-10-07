<script setup>
defineProps({ name: { type: String, required: true }, size: { type: Number, default: 18 } })

// 线性图标路径（24x24 视图），避免引入整套图标库
const PATHS = {
  home: 'M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z',
  grid: 'M3 4h18v16H3zM3 10h18M9 4v16',
  coins: 'M12 3a8 3 0 1 0 0 6 8 3 0 1 0 0-6zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6',
  bell: 'M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4',
  chart: 'M3 3v18h18M7 15l4-4 3 3 5-6',
  target: 'M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20zM12 6a6 6 0 1 0 0 12 6 6 0 1 0 0-12zM12 10a2 2 0 1 0 0 4 2 2 0 1 0 0-4z',
  star: 'm12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z',
  sun: 'M12 7a5 5 0 1 0 0 10 5 5 0 1 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  auto: 'M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20zM12 2v20',
  menu: 'M3 6h18M3 12h18M3 18h18',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 1 0 0-14zM21 21l-4.3-4.3',
  external: 'M14 3h7v7M10 14 21 3M19 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6',
  download: 'M12 3v12M7 10l5 5 5-5M4 21h16',
  back: 'M15 18l-6-6 6-6',
  help: 'M12 2a10 10 0 1 0 0 20 10 10 0 1 0 0-20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01',
  close: 'M18 6 6 18M6 6l12 12',
  columns: 'M3 4h18v16H3zM9 4v16M15 4v16',
  book: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5',
  buy: 'M3 17l6-6 4 4 8-8M15 7h6v6',
  sell: 'M3 7l6 6 4-4 8 8M15 17h6v-6',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  user: 'M12 3a4 4 0 1 0 0 8 4 4 0 1 0 0-8zM4 21a8 8 0 0 1 16 0',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  shield: 'M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z',
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path :d="PATHS[name]" />
  </svg>
</template>
