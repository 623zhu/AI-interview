<template>
  <div class="home">
    <!-- Welcome / upload state -->
    <div v-if="!resume" class="home__welcome">
      <h2>开始新面试</h2>
      <p class="sub">上传简历，AI 将为你进行模拟面试</p>

      <div v-if="uploading" class="uploading-state">
        <div class="spinner" />
        <p>正在解析简历…</p>
      </div>

      <el-upload
        v-else
        class="upload-zone"
        :action="uploadUrl"
        :headers="uploadHeaders"
        :accept="'.pdf,.docx'"
        :on-success="onUploaded"
        :on-error="onError"
        :before-upload="beforeUpload"
        :show-file-list="false"
        drag
      >
        <div class="upload-zone__inner">
          <span class="upload-icon">📄</span>
          <p class="upload-text">拖拽或点击上传简历</p>
          <p class="upload-hint">支持 PDF、DOCX 格式，最大 10MB</p>
        </div>
      </el-upload>
    </div>

    <!-- Resume ready -->
    <div v-else class="home__ready">
      <div class="file-badge">
        <span>{{ statusIcon }}</span>
        <span class="file-name">{{ resume.original_filename }}</span>
        <el-tag :type="statusTagType" size="small">{{ statusText }}</el-tag>
      </div>

      <div v-if="resume.parse_status === 'completed'" class="start-box">
        <h3 class="section-title">选择面试岗位</h3>
        <div v-if="jobList.length === 0" class="job-empty">
          <p>暂无可用岗位，请联系管理员在后台添加</p>
        </div>
        <div v-else class="job-grid">
          <div
            v-for="j in jobList"
            :key="j.id"
            class="job-card"
            :class="{ selected: selectedJob?.id === j.id }"
            @click="selectedJob = selectedJob?.id === j.id ? null : j"
          >
            <div class="job-card__head">
              <span class="job-card__title">{{ j.title }}</span>
              <el-icon v-if="selectedJob?.id === j.id" class="job-card__check"><CircleCheckFilled /></el-icon>
            </div>
            <div class="job-card__tags">
              <el-tag size="small" type="info">{{ j.category }}</el-tag>
              <el-tag size="small" :type="levelType(j.level)">{{ j.level }}</el-tag>
            </div>
            <div v-if="j.skill_domains" class="job-card__skills">
              <el-tag v-for="d in j.skill_domains" :key="d" size="small" effect="plain" round>{{ d }}</el-tag>
            </div>
          </div>
        </div>
        <div v-if="selectedJob" class="job-actions">
          <el-button type="primary" size="large" :loading="creating" @click="startInterview">
            开始「{{ selectedJob.title }}」面试
          </el-button>
        </div>
      </div>

      <div v-else-if="resume.parse_status === 'failed'" class="error-box">
        ⚠️ 解析失败：{{ resume.parse_error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'
import { jobApi } from '@/api/jobs'

const router = useRouter()
const authStore = useAuthStore()

const resume = ref<any>(null)

interface JobCard { id: string; title: string; category: string; level: string; skill_domains: string[] }
const selectedJob = ref<JobCard | null>(null)
const jobList = ref<JobCard[]>([])
const uploading = ref(false)
const creating = ref(false)

const uploadUrl = '/api/v1/resumes/upload?auto_parse=true'
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${authStore.accessToken}` }))

const statusIcon = computed(() => {
  const m: Record<string, string> = { completed: '✅', processing: '⏳', pending: '📄', failed: '❌' }
  return m[resume.value?.parse_status] || '📄'
})
const statusTagType = computed(() => {
  const m: Record<string, string> = { completed: 'success', processing: 'warning', pending: 'info', failed: 'danger' }
  return m[resume.value?.parse_status] || 'info'
})
const statusText = computed(() => {
  const m: Record<string, string> = { completed: '解析完成', processing: '解析中…', pending: '等待解析', failed: '解析失败' }
  return m[resume.value?.parse_status] || '未知'
})

function beforeUpload(file: File) {
  const ok = file.type === 'application/pdf' || file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  if (!ok) { ElMessage.error('仅支持 PDF / DOCX'); return false }
  if (file.size > 10 * 1024 * 1024) { ElMessage.error('最大 10MB'); return false }
  uploading.value = true
  return true
}
function onUploaded(response: any) {
  uploading.value = false
  if (response.code === 201) {
    resume.value = response.data
    if (response.data.parse_status === 'completed') ElMessage.success('简历解析完成')
    else if (response.data.parse_status === 'failed') ElMessage.warning('上传成功，解析失败')
    else ElMessage.success('上传成功，解析中…')
  }
}
function onError() { uploading.value = false; ElMessage.error('上传失败') }

function levelType(level: string) {
  const m: Record<string, string> = { junior: 'info', mid: 'warning', senior: 'danger', lead: '' }
  return m[level] || 'info'
}

onMounted(async () => {
  try {
    const { data } = await jobApi.list({ include_inactive: false, page_size: 100 })
    jobList.value = (data.data.items || []).map((j: any) => ({
      id: j.id, title: j.title, category: j.category, level: j.level || 'mid',
      skill_domains: [],
    }))
    for (const j of jobList.value) {
      try {
        const { data: d } = await jobApi.get(j.id)
        if (d.data.skill_tree?.domains) {
          j.skill_domains = d.data.skill_tree.domains.map((d: any) => d.name)
        }
      } catch { /* skip */ }
    }
  } catch { /* ignore */ }
})

async function startInterview() {
  if (creating.value || !selectedJob.value) return
  creating.value = true
  try {
    const { data: res } = await apiClient.post('/interviews', {
      resume_id: resume.value.id,
      job_id: selectedJob.value.id,
      config: { max_turns: 12, max_duration_minutes: 45 },
    })
    if (res.code === 201) router.push(`/interview/${res.data.id}`)
    else ElMessage.error(res.message || '创建面试失败')
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || '创建面试失败') }
  finally { creating.value = false }
}
</script>

<style scoped>
.home { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100%; padding: 48px 24px; }
.home__welcome { text-align: center; max-width: 460px; width: 100%; }
.home__welcome h2 { font-size: 28px; font-weight: 700; color: #1f2937; margin-bottom: 8px; }
.sub { font-size: 14px; color: #6b7280; margin-bottom: 32px; }

.uploading-state { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px; color: #6b7280; font-size: 14px; }
.spinner { width: 32px; height: 32px; border: 3px solid #e5e7eb; border-top-color: #4f46e5; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.upload-zone { width: 100%; }
.upload-zone :deep(.el-upload-dragger) { padding: 56px 24px; border-radius: 16px; border: 2px dashed #e5e7eb; }
.upload-zone__inner { text-align: center; }
.upload-icon { font-size: 48px; display: block; margin-bottom: 16px; }
.upload-text { font-size: 16px; color: #374151; font-weight: 500; }
.upload-hint { font-size: 13px; color: #9ca3af; margin-top: 8px; }

.home__ready { max-width: 700px; width: 100%; }
.file-badge { display: flex; align-items: center; gap: 10px; padding: 12px 16px; background: #f3f4f6; border-radius: 10px; margin-bottom: 24px; font-size: 14px; }
.file-name { flex: 1; font-weight: 500; color: #374151; }
.start-box { display: flex; flex-direction: column; gap: 16px; }
.error-box { color: #ef4444; font-size: 13px; padding: 12px 16px; background: #fef2f2; border-radius: 10px; }

.section-title { font-size: 18px; margin: 0; }
.job-empty { text-align: center; padding: 40px; color: #999; background: #fafafa; border-radius: 8px; }
.job-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.job-card {
  background: #fff; border: 2px solid #e8e8e8; border-radius: 10px;
  padding: 16px 18px; cursor: pointer; transition: all .2s; position: relative;
}
.job-card:hover { border-color: #a0c4ff; box-shadow: 0 2px 8px rgba(64,158,255,.1); }
.job-card.selected { border-color: #409eff; background: #f0f7ff; box-shadow: 0 2px 12px rgba(64,158,255,.15); }
.job-card__head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.job-card__title { font-size: 15px; font-weight: 600; color: #1f2937; }
.job-card__check { color: #409eff; font-size: 20px; }
.job-card__tags { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.job-card__skills { display: flex; gap: 4px; flex-wrap: wrap; }
.job-actions { margin-top: 8px; text-align: center; }
</style>
