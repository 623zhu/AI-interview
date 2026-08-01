<template>
  <div class="resume-page">
    <h2 class="page-title">📋 我的简历</h2>

    <el-card class="dash-card" v-loading="loading">
      <div v-if="!resume" class="resume-empty">
        <p class="resume-empty__hint">还没有上传简历，选择你的简历文件开始吧</p>
        <div v-if="uploading" class="uploading-box">
          <el-icon :size="40" class="uploading-box__icon"><Loading /></el-icon>
          <p class="uploading-box__text">正在上传并解析简历...</p>
          <p class="uploading-box__sub">请稍候，大文件可能需要几秒钟</p>
        </div>
        <el-upload
          v-else :action="uploadUrl" :headers="uploadHeaders" :accept="'.pdf,.docx'"
          :on-success="onUploadSuccess" :on-error="onUploadError"
          :before-upload="beforeUpload" :show-file-list="false" drag
        >
          <el-icon :size="48"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽或<em>点击上传</em></div>
          <template #tip><div class="el-upload__tip">支持 PDF、DOCX 格式，大小不超过 10MB</div></template>
        </el-upload>
      </div>

      <div v-else class="resume-done">
        <div class="resume-done__info">
          <span class="resume-done__icon">{{ statusIcon }}</span>
          <span class="resume-done__name">{{ resume.original_filename }}</span>
          <el-tag :type="statusTagType" size="small">{{ statusText }}</el-tag>
        </div>
        <div v-if="resume.parse_status === 'failed' && resume.parse_error" class="resume-done__error">
          ⚠️ {{ resume.parse_error }}
        </div>

        <div class="resume-done__actions">
          <el-upload
            :action="uploadUrl" :headers="uploadHeaders" :accept="'.pdf,.docx'"
            :on-success="onUploadSuccess" :before-upload="beforeUpload" :show-file-list="false"
          >
            <el-button size="small">🔄 重新上传</el-button>
          </el-upload>
          <el-button size="small" type="danger" plain @click="deleteResume">🗑 删除</el-button>
        </div>

      </div>
    </el-card>

    <!-- Job Selection -->
    <div v-if="resume?.parse_status === 'completed'" class="job-section">
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

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Loading, CircleCheckFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'
import { jobApi } from '@/api/jobs'

const authStore = useAuthStore()
const router = useRouter()

const loading = ref(false)
const uploading = ref(false)
const creating = ref(false)
const resume = ref<any>(null)

interface JobCard {
  id: string
  title: string
  category: string
  level: string
  skill_domains: string[]
}
const selectedJob = ref<JobCard | null>(null)
const jobList = ref<JobCard[]>([])

const uploadUrl = '/api/v1/resumes/upload?auto_parse=true'
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${authStore.accessToken}` }))

const statusIcon = computed(() => {
  const map: Record<string, string> = { completed: '✅', processing: '⏳', pending: '📄', failed: '❌' }
  return map[resume.value?.parse_status] || '📄'
})
const statusTagType = computed(() => {
  const map: Record<string, string> = { completed: 'success', processing: 'warning', pending: 'info', failed: 'danger' }
  return map[resume.value?.parse_status] || 'info'
})
const statusText = computed(() => {
  const map: Record<string, string> = { completed: '解析完成', processing: '解析中...', pending: '等待解析', failed: '解析失败' }
  return map[resume.value?.parse_status] || '未知'
})

function beforeUpload(file: File) {
  const isAllowed = file.type === 'application/pdf' ||
    file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  if (!isAllowed) { ElMessage.error('仅支持 PDF 和 DOCX 格式'); return false }
  if (file.size > 10 * 1024 * 1024) { ElMessage.error('文件大小不能超过 10MB'); return false }
  uploading.value = true
  return true
}

function onUploadSuccess(response: any) {
  uploading.value = false
  if (response.code === 201) {
    resume.value = response.data
    if (response.data.parse_status === 'completed') ElMessage.success('上传成功，解析完成')
    else if (response.data.parse_status === 'failed') ElMessage.warning('上传成功，但解析失败')
    else ElMessage.success('上传成功，正在解析…')
  }
}

function onUploadError() { uploading.value = false; ElMessage.error('上传失败，请重试') }

async function deleteResume() {
  try {
    await ElMessageBox.confirm('确定要删除该简历吗？', '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await apiClient.delete(`/resumes/${resume.value.id}`)
    resume.value = null; selectedJob.value = null
    ElMessage.success('简历已删除')
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString() !== 'cancel') ElMessage.error('删除失败')
  }
}

function levelType(level: string) {
  const m: Record<string, string> = { junior: 'info', mid: 'warning', senior: 'danger', lead: '' }
  return m[level] || 'info'
}

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

onMounted(async () => {
  try {
    const { data: res } = await apiClient.get('/dashboard')
    resume.value = res.data.resume
  } catch { /* ignore */ }
  try {
    const { data } = await jobApi.list({ include_inactive: false, page_size: 100 })
    jobList.value = (data.data.items || []).map((j: any) => ({
      id: j.id, title: j.title, category: j.category, level: j.level || 'mid',
      skill_domains: [],
    }))
    // Enrich with skill tree domains
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
</script>

<style scoped>
.resume-page { max-width: 700px; margin: 0 auto; }
.page-title { font-size: 22px; margin-bottom: 20px; color: #333; }
.dash-card { margin-bottom: 20px; }
.resume-empty__hint { color: #999; margin-bottom: 16px; }

.uploading-box {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 180px; border: 2px dashed var(--el-color-primary-light-5);
  border-radius: 8px; background: var(--el-color-primary-light-9);
}
.uploading-box__icon { color: var(--el-color-primary); animation: spin 1.2s linear infinite; }
.uploading-box__text { margin-top: 12px; font-size: 15px; color: #333; font-weight: 500; }
.uploading-box__sub { margin-top: 6px; font-size: 12px; color: #999; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.resume-done__info { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.resume-done__icon { font-size: 18px; }
.resume-done__name { font-weight: 600; font-size: 15px; }
.resume-done__error { color: #f56c6c; font-size: 12px; margin-bottom: 12px; padding: 8px 12px; background: #fef0f0; border-radius: 6px; }

.resume-done__actions { display: flex; gap: 8px; }

.job-section { margin-top: 24px; }
.section-title { font-size: 18px; margin-bottom: 16px; }

.job-empty { text-align: center; padding: 40px; color: #999; background: #fafafa; border-radius: 8px; }

.job-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }

.job-card {
  background: #fff; border: 2px solid #e8e8e8; border-radius: 10px;
  padding: 16px 18px; cursor: pointer; transition: all .2s;
  position: relative;
}
.job-card:hover { border-color: #a0c4ff; box-shadow: 0 2px 8px rgba(64,158,255,.1); }
.job-card.selected { border-color: #409eff; background: #f0f7ff; box-shadow: 0 2px 12px rgba(64,158,255,.15); }

.job-card__head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.job-card__title { font-size: 16px; font-weight: 600; color: #1f2937; }
.job-card__check { color: #409eff; font-size: 20px; }

.job-card__tags { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.job-card__skills { display: flex; gap: 4px; flex-wrap: wrap; }

.job-actions { margin-top: 20px; text-align: center; }

</style>
