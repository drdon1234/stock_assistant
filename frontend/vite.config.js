import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 构建产物输出到 Python 包内，由 Tornado 直接托管；开发时 /api 代理到本地后端
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: fileURLToPath(new URL('../instock/web/dist', import.meta.url)),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) return 'echarts'
          if (id.includes('node_modules/ag-grid')) return 'ag-grid'
          if (id.includes('node_modules/naive-ui') || id.includes('node_modules/vueuc') || id.includes('node_modules/@css-render')) return 'naive'
        },
      },
    },
  },
  server: {
    proxy: { '/api': 'http://localhost:9988' },
  },
})
