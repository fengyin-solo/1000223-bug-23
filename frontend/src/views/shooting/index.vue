<template>
  <section class="page" data-module="shooting">
    <header class="page-head">
      <div>
        <h2>拍摄进度管理</h2>
        <p class="page-desc">维护拍摄日，围绕拍摄日编号、拍摄日期、拍摄地点、计划场次做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记拍摄日</button>
        <button class="btn" type="button" :disabled="retrying" @click="retryPending">
          {{ retrying ? '重试中…' : '中断重试' }}
        </button>
        <button class="btn" type="button" @click="exportRows">导出拍摄进度清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayCell(row, column) }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              :disabled="busyId === String(row.id)"
              @click="runAction(action, row)"
            >
              {{ busyId === String(row.id) ? '处理中…' : action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            {{ readFailed ? '拍摄日列表读取失败，可点击「中断重试」后重新查询' : '暂无拍摄进度数据，可先登记拍摄日' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ readFailed ? 0 : total }} 条拍摄进度记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ActionResponse = { ok: boolean; message: string; entry: Row | null }

const ENDPOINT = '/api/shooting'
const columns = ["拍摄日编号", "拍摄日期", "拍摄地点", "计划场次", "完成场次", "有效工时", "超时情况", "拍摄状态"]
const actions = ["开始拍摄", "确认收工", "申请顺延"]

const stats = ref([
  { label: "计划拍摄日", value: 0 },
  { label: "已完成拍摄日", value: 0 },
  { label: "顺延天数", value: 0 },
])

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const readFailed = ref(false)
const retrying = ref(false)
const busyId = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function displayCell(row: Row, column: string): string {
  const value = row[column]
  if (value === null || value === undefined) return '暂无'
  const text = String(value).trim()
  return text.length ? text : '暂无'
}

function availableActions(row: Row): string[] {
  // 已收工是终态，不再给出动作入口，避免误操作改动收工结果。
  return String(row.status ?? '') === '已收工' ? [] : actions
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '拍摄日登记入口尚未接入审批流'
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    if (Array.isArray(payload.cards)) {
      stats.value = payload.cards
    }
  } catch {
    // 统计读不到时保留现有卡片并在列表错误提示中体现，不阻断列表使用。
  }
}

async function retryPending() {
  errorMessage.value = ''
  retrying.value = true
  try {
    const response = await request(`${ENDPOINT}/retry`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const payload = (await response.json()) as ActionResponse
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '中断重试未生效，请稍后再试')
    }
    // 重试只更新未完成项，随后重新拉取，列表/详情/概览口径重新对齐。
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '中断重试失败'
  } finally {
    retrying.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  busyId.value = String(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as ActionResponse
    if (!response.ok || !payload.ok) {
      // 后端拒绝（如已收工再操作）时保留现状，只提示原因，不覆盖本地数据。
      throw new Error(payload.message || '拍摄进度动作未生效，请稍后重试')
    }
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '拍摄进度操作失败'
  } finally {
    busyId.value = ''
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('拍摄日列表读取失败')
    }
    const payload = await response.json()
    if (!Array.isArray(payload.items)) {
      throw new Error('拍摄日列表数据格式异常')
    }
    rows.value = payload.items
    total.value = payload.total ?? rows.value.length
    readFailed.value = false
  } catch (error) {
    // 读取失败或返回异常时清空旧数据，避免页面继续显示上一条已完成场次。
    rows.value = []
    total.value = 0
    readFailed.value = true
    errorMessage.value = error instanceof Error ? error.message : '拍摄进度列表读取失败'
  }
}

onMounted(() => {
  void Promise.all([reload(), reloadStats()])
})
</script>
