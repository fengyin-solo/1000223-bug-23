<template>
  <section class="page" data-module="shooting">
    <header class="page-head">
      <div>
        <h2>拍摄进度管理</h2>
        <p class="page-desc">维护拍摄日，围绕拍摄日编号、拍摄日期、拍摄地点、计划场次做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记拍摄日</button>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无拍摄进度数据，可先登记拍摄日</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条拍摄进度记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/shooting'
const columns = ["拍摄日编号", "拍摄日期", "拍摄地点", "计划场次", "完成场次", "有效工时", "超时情况", "拍摄状态"]
const actions = ["开始拍摄", "确认收工", "申请顺延"]
const statuses = ["待拍摄", "拍摄中", "已收工", "已顺延"]
const stats = [{"label": "计划拍摄日", "value": 0}, {"label": "已完成拍摄日", "value": 0}, {"label": "顺延天数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

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

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  let actionError = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const result = await response.json().catch(() => null)
    if (!response.ok || !result || result.ok === false) {
      actionError = result?.message || '拍摄进度动作未生效，请稍后重试'
    }
  } catch (error) {
    actionError = error instanceof Error ? error.message : '拍摄进度操作失败'
  }
  // 无论动作成功、被拦截还是请求中断，都重新拉取列表与服务端对齐；
  // 服务端对已完成项幂等，中断后重试只会更新未完成的拍摄日
  await reload()
  if (actionError) {
    errorMessage.value = actionError
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
    rows.value = payload?.items ?? []
    total.value = payload?.total ?? 0
  } catch (error) {
    // 读取失败或返回空数据时清空列表，不再展示上次加载的完成场次
    rows.value = []
    total.value = 0
    errorMessage.value = error instanceof Error ? error.message : '拍摄进度列表读取失败'
  }
}

onMounted(reload)
</script>
