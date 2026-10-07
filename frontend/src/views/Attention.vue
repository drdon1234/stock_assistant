<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NButton, NEmpty, NSpin, useMessage } from 'naive-ui'
import GuideButton from '../components/GuideButton.vue'
import PageGuide from '../components/PageGuide.vue'
import { api } from '../api'
import { fmtMoney, fmtNum, fmtPct, fmtPercent, trendClass } from '../format'
import { toggleAttention } from '../store'

const message = useMessage()
const items = ref([])
const loading = ref(true)
document.title = '我的关注 · InStock'

async function load() {
  loading.value = true
  try {
    items.value = (await api.attention()).items
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function remove(code) {
  await toggleAttention(code)
  items.value = items.value.filter((i) => i.code !== code)
}

load()
</script>

<template>
  <div class="page">
    <div class="toolbar"><h1>我的关注</h1><GuideButton id="attention" /><span class="muted">{{ items.length }} 只</span></div>
    <PageGuide id="attention" />
    <NSpin :show="loading">
      <NEmpty v-if="!loading && !items.length" description="还没有关注的股票，在数据表或个股页点击 ☆ 添加" class="card empty" />
      <div v-else class="list">
        <div v-for="item in items" :key="item.code" class="card item">
          <RouterLink :to="`/stock/${item.code}`" class="name">
            <b>{{ item.name || item.code }}</b>
            <span class="muted">{{ item.code }}</span>
          </RouterLink>
          <div class="quote">
            <span class="price" :class="trendClass(item.change_rate)">{{ fmtNum(item.new_price) }}</span>
            <span :class="trendClass(item.change_rate)">{{ fmtPct(item.change_rate) }}</span>
          </div>
          <div class="muted meta">
            <span>换手 {{ fmtPercent(item.turnoverrate) || '-' }}</span>
            <span>成交 {{ fmtMoney(item.deal_amount) || '-' }}</span>
          </div>
          <NButton size="tiny" quaternary class="remove" @click="remove(item.code)">取消关注</NButton>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.item { padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; position: relative; }
.name { display: flex; align-items: baseline; gap: 8px; color: var(--text); text-decoration: none; }
.quote { display: flex; align-items: baseline; gap: 10px; }
.price { font-size: 22px; font-weight: 700; }
.meta { display: flex; gap: 12px; font-size: 12px; }
.remove { position: absolute; top: 10px; right: 8px; }
.empty { padding: 48px 0; }
</style>
