<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, User, DataBoard, Medal, WarningFilled } from '@element-plus/icons-vue'
import { adminApi, type AdminUserItem, type AdminUserDetail } from '@/api/admin'

const loading = ref(false)
const users = ref<AdminUserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

// Detail drawer
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AdminUserDetail | null>(null)

// ── Fetch list ──
async function fetchUsers() {
  loading.value = true
  try {
    const res = await adminApi.getUsers({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    if (res.data.code === 200) {
      users.value = res.data.data.items
      total.value = res.data.data.total
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  fetchUsers()
}

function onPageChange(p: number) {
  page.value = p
  fetchUsers()
}

function onSizeChange(s: number) {
  pageSize.value = s
  page.value = 1
  fetchUsers()
}

// ── Detail drawer ──
async function showDetail(userId: string) {
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const res = await adminApi.getUserDetail(userId)
    if (res.data.code === 200) {
      detail.value = res.data.data
    }
  } catch (e: any) {
    ElMessage.error('加载用户详情失败')
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// ── Toggle status ──
async function toggleActive(user: AdminUserItem) {
  const action = user.is_active ? '禁用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确定要${action}用户「${user.username}」吗？`,
      `${action}用户`,
      { confirmButtonText: action, cancelButtonText: '取消', type: 'warning' }
    )
    const res = await adminApi.updateUser(user.id, { is_active: !user.is_active })
    if (res.data.code === 200) {
      user.is_active = !user.is_active
      ElMessage.success(`已${action}用户`)
    }
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.detail || `${action}失败`)
    }
  }
}

onMounted(fetchUsers)
</script>

<template>
  <div class="user-manage">
    <div class="page-header">
      <h2>用户管理</h2>
      <el-button :icon="Refresh" @click="fetchUsers" :loading="loading">刷新</el-button>
    </div>

    <!-- Search bar -->
    <el-card class="filter-card">
      <el-input
        v-model="keyword"
        placeholder="搜索用户名或邮箱"
        :prefix-icon="Search"
        clearable
        style="width: 280px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button type="primary" @click="onSearch" style="margin-left: 10px">搜索</el-button>
    </el-card>

    <!-- User table -->
    <el-card>
      <el-table :data="users" stripe v-loading="loading" empty-text="暂无用户数据">
        <el-table-column prop="username" label="用户名" min-width="110">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px">
              <el-avatar :size="28" :icon="User" />
              <span style="font-weight: 500">{{ row.username }}</span>
              <el-tag v-if="row.is_admin" size="small" type="danger" effect="dark">管理员</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column prop="interview_count" label="面试次数" width="90" align="center" sortable />
        <el-table-column prop="avg_score" label="平均分" width="80" align="center" sortable>
          <template #default="{ row }">
            <span v-if="row.avg_score !== null" :style="{ color: row.avg_score >= 80 ? '#67c23a' : row.avg_score >= 60 ? '#e6a23c' : '#f56c6c', fontWeight: 600 }">
              {{ row.avg_score }}
            </span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_activity" label="最近活动" width="160">
          <template #default="{ row }">
            {{ row.last_activity ? new Date(row.last_activity).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" width="160">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="showDetail(row.id)">详情</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              link
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; text-align: right">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <!-- User Detail Drawer -->
    <el-drawer v-model="drawerVisible" title="用户详情" size="480px" :loading="detailLoading">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户名">{{ detail.username }}</el-descriptions-item>
          <el-descriptions-item label="邮箱">{{ detail.email }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag :type="detail.is_admin ? 'danger' : 'info'" size="small">
              {{ detail.is_admin ? '管理员' : '普通用户' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="detail.is_active ? 'success' : 'danger'" size="small">
              {{ detail.is_active ? '正常' : '已禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">
            {{ detail.created_at ? new Date(detail.created_at).toLocaleString() : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="面试次数">
            {{ detail.stats.interview_count }}
          </el-descriptions-item>
          <el-descriptions-item label="平均分" :span="2">
            <span v-if="detail.stats.avg_score !== null" :style="{ color: detail.stats.avg_score >= 80 ? '#67c23a' : detail.stats.avg_score >= 60 ? '#e6a23c' : '#f56c6c', fontWeight: 600, fontSize: '18px' }">
              {{ detail.stats.avg_score }}
            </span>
            <span v-else style="color: #c0c4cc">暂无评分</span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top: 24px; margin-bottom: 12px;">最近面试记录</h4>
        <el-table :data="detail.recent_interviews" size="small" stripe empty-text="暂无面试记录" max-height="400">
          <el-table-column prop="job_title" label="岗位" min-width="120" />
          <el-table-column prop="status" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'in_progress' ? 'warning' : 'info'" size="small">
                {{ row.status === 'completed' ? '已完成' : row.status === 'in_progress' ? '进行中' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="评分" width="60" align="center">
            <template #default="{ row }">
              <span v-if="row.score !== null" :style="{ color: row.score >= 80 ? '#67c23a' : row.score >= 60 ? '#e6a23c' : '#f56c6c' }">{{ row.score }}</span>
              <span v-else style="color: #c0c4cc">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="150">
            <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</template>
          </el-table-column>
        </el-table>
      </template>
      <el-skeleton v-else :rows="6" animated />
    </el-drawer>
  </div>
</template>

<style scoped>
.user-manage {
  padding: 0 4px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
}

.filter-card {
  margin-bottom: 16px;
}
</style>
