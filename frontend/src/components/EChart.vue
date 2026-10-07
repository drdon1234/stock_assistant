<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { use, init } from 'echarts/core'
import { BarChart, CandlestickChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  AxisPointerComponent, DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent, MarkPointComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { isDark } from '../store'

use([BarChart, CandlestickChart, CustomChart, LineChart, ScatterChart, AxisPointerComponent, DataZoomComponent,
  GridComponent, LegendComponent, MarkLineComponent, MarkPointComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({ option: { type: Object, required: true } })
const emit = defineEmits(['ready'])
const el = ref(null)
const chart = shallowRef(null)
let observer

function create() {
  chart.value?.dispose()
  chart.value = init(el.value, isDark.value ? 'dark' : null, { renderer: 'canvas' })
  chart.value.setOption({ backgroundColor: 'transparent', ...props.option }, true)
  emit('ready', chart.value)
}

onMounted(() => {
  create()
  observer = new ResizeObserver(() => chart.value?.resize())
  observer.observe(el.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
})
watch(() => props.option, (option) => chart.value?.setOption({ backgroundColor: 'transparent', ...option }, true))
watch(isDark, create)

defineExpose({ chart })
</script>

<template>
  <div ref="el" class="echart" />
</template>

<style scoped>
.echart { width: 100%; height: 100%; min-height: 120px; }
</style>
