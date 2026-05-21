<template>
  <div class="routes-page">
    <h2>路由表</h2>

    <el-form :inline="true" class="filter-bar">
      <el-form-item label="目标网络">
        <el-input v-model="filters.cidr" placeholder="输入 CIDR" clearable style="width:180px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="fetchData">查询</el-button>
        <el-button @click="filters.cidr='';fetchData()">重置</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column type="index" width="50" />
      <el-table-column prop="target_network" label="目标网络" min-width="140" />
      <el-table-column prop="subnet_mask" label="子网掩码" min-width="140" />
      <el-table-column prop="cidr" label="CIDR" min-width="160" />
      <el-table-column prop="gateway" label="网关" min-width="130" />
      <el-table-column prop="interface_name" label="接口" min-width="150" show-overflow-tooltip />
      <el-table-column prop="route_type" label="类型" width="80" />
      <el-table-column prop="protocol" label="协议" width="80" />
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString() }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        :page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="fetchData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/api'

const items = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(50)
const total = ref(0)
const filters = reactive({ cidr: '' })

async function fetchData() {
  loading.value = true
  try {
    const { data } = await api.get('/results/routes', {
      params: { page: page.value, size: size.value, cidr: filters.cidr }
    })
    items.value = data.items
    total.value = data.total
  } catch { /* handled */ }
  finally { loading.value = false }
}

onMounted(fetchData)
</script>

<style scoped>
.routes-page h2 { margin: 0 0 16px; }
.filter-bar { margin-bottom: 12px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
