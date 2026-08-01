<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Upload } from '@element-plus/icons-vue'
import { questionApi } from '@/api/questions'
import type { QuestionImportItem, QuestionImportResult } from '@/types/question'

const router = useRouter()

// ── State ──
const activeTab = ref<'csv' | 'json'>('csv')
const importing = ref(false)
const result = ref<QuestionImportResult | null>(null)

// CSV
const csvText = ref('')
const csvParsedTitle = ref('')

// JSON
const jsonText = ref('')
const parsedItems = ref<QuestionImportItem[] | null>(null)

const categoryOptions = [
  { label: '概念理解', value: 'concept' },
  { label: '原理理解', value: 'principle' },
  { label: '工程实践', value: 'practice' },
  { label: '优化能力', value: 'optimization' },
  { label: '系统设计', value: 'design' },
]

const difficultyOptions = ['easy', 'medium', 'hard']

// ── CSV tab ──
function handleFileUpload(file: File) {
  result.value = null
  const reader = new FileReader()
  reader.onload = (e) => {
    csvText.value = e.target?.result as string
    csvParsedTitle.value = file.name
  }
  reader.readAsText(file, 'UTF-8')
}

function parseCSV(): QuestionImportItem[] {
  const lines = csvText.value
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(l => l.length > 0)

  if (lines.length < 2) {
    throw new Error('CSV 至少需要标题行 + 一行数据')
  }

  // Parse header
  const headers = parseCSVLine(lines[0])
  console.log('CSV headers:', headers)

  const items: QuestionImportItem[] = []
  const errors: string[] = []

  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i])
    if (values.length === 0) continue

    const row: Record<string, string> = {}
    headers.forEach((h, idx) => { row[h.trim()] = (values[idx] || '').trim() })

    // 三个必填字段：题目内容、核心点、参考答案
    const content = (row['题目'] || row['内容'] || row['content'] || '').trim()
    if (!content) {
      errors.push(`第 ${i + 1} 行: 缺少题目内容`)
      continue
    }

    const expectedPoints = (row['核心点'] || row['评分指引'] || row['expected_points'] || '').trim()
    if (!expectedPoints) {
      errors.push(`第 ${i + 1} 行: 缺少核心点/评分指引`)
      continue
    }

    const referenceAnswer = (row['参考答案'] || row['reference_answer'] || '').trim()
    if (!referenceAnswer) {
      errors.push(`第 ${i + 1} 行: 缺少参考答案`)
      continue
    }

    // 可选字段（有默认值）
    const category = row['分类'] || row['category'] || 'basic'
    if (!categoryOptions.find(c => c.value === category)) {
      errors.push(`第 ${i + 1} 行: 无效分类 "${category}"，已使用默认值 concept`)
      // 不中断，使用默认值继续
    }

    const difficulty = row['难度'] || row['difficulty'] || 'medium'
    if (!difficultyOptions.includes(difficulty)) {
      // 不中断，使用默认值
    }

    items.push({
      content,
      expected_points: expectedPoints,
      reference_answer: referenceAnswer,
      category: categoryOptions.find(c => c.value === category) ? category : 'concept',
      difficulty: difficultyOptions.includes(difficulty) ? difficulty : 'medium',
    })
  }

  if (errors.length > 0) {
    ElMessage.warning(errors.slice(0, 3).join('; ') + (errors.length > 3 ? '...' : ''))
  }

  return items
}

function parseCSVLine(line: string): string[] {
  const result: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      result.push(current)
      current = ''
    } else {
      current += ch
    }
  }
  result.push(current)
  return result
}

const csvSample = `题目,核心点,参考答案,分类,难度
请解释数据库事务的ACID特性,考察对事务核心特性的理解。需能说出原子性、一致性、隔离性、持久性的含义并能举例说明,事务是数据库操作的最小工作单元，具有ACID四个特性：原子性(Atomicity)指事务中的所有操作要么全部成功要么全部失败回滚；一致性(Consistency)指事务执行前后数据库都处于一致状态...,concept,medium
请描述你在项目中遇到的最大挑战,"考察项目经验和问题解决能力。关注候选人如何分析问题、采取什么措施、最终结果如何。好的回答应包含具体场景和量化结果","在上一家公司的电商项目中，我遇到过数据库性能瓶颈。通过分析慢查询日志，发现几个关键SQL缺少索引，优化后QPS从200提升到800...",practice,medium`

function loadCsvSample() {
  csvText.value = csvSample
  csvParsedTitle.value = ''
}

// ── JSON tab ──
const jsonSample = `[
  {
    "content": "请解释数据库事务的ACID特性",
    "expected_points": "考察对事务核心特性的理解。需能说出原子性、一致性、隔离性、持久性的含义，并能举例说明。",
    "reference_answer": "事务是数据库操作的最小工作单元，具有ACID四个特性...",
    "category": "basic",
    "difficulty": "medium"
  }
]`

function parseJSON() {
  result.value = null
  try {
    const data = JSON.parse(jsonText.value)
    if (!Array.isArray(data)) {
      ElMessage.error('JSON 必须是数组')
      return
    }
    for (let i = 0; i < data.length; i++) {
      const item = data[i]
      // 三个必填字段：内容、核心点、参考答案
      if (!item.content) {
        ElMessage.error(`第 ${i + 1} 项缺少必填字段: content(题目内容)`)
        return
      }
      if (!item.expected_points) {
        ElMessage.error(`第 ${i + 1} 项缺少必填字段: expected_points(核心点/评分指引)`)
        return
      }
      if (!item.reference_answer) {
        ElMessage.error(`第 ${i + 1} 项缺少必填字段: reference_answer(参考答案)`)
        return
      }
      item.category = item.category || 'basic'
      item.difficulty = item.difficulty || 'medium'
      item.job_category = item.job_category || null
    }
    parsedItems.value = data
    ElMessage.success(`解析成功，共 ${data.length} 条题目`)
  } catch (e: any) {
    ElMessage.error(`JSON 格式错误: ${e.message}`)
    parsedItems.value = null
  }
}

// ── Import ──
async function doImport() {
  let items: QuestionImportItem[] | null = null

  if (activeTab.value === 'csv') {
    if (!csvText.value.trim()) {
      ElMessage.warning('请先上传或粘贴 CSV 数据')
      return
    }
    try {
      items = parseCSV()
      if (items.length === 0) {
        ElMessage.warning('未解析到有效数据')
        return
      }
    } catch (e: any) {
      ElMessage.error(e.message)
      return
    }
  } else {
    items = parsedItems.value
    if (!items || items.length === 0) {
      ElMessage.warning('请先解析 JSON 数据')
      return
    }
  }

  importing.value = true
  try {
    const res = await questionApi.importItems(items)
    result.value = res.data.data
    if (result.value?.failed === 0) {
      ElMessage.success(`成功导入 ${result.value?.success} 条题目`)
    } else {
      ElMessage.warning(`导入完成: 成功 ${result.value?.success}, 失败 ${result.value?.failed}`)
    }
    // Clear
    if (activeTab.value === 'csv') {
      csvText.value = ''
      csvParsedTitle.value = ''
    } else {
      parsedItems.value = null
      jsonText.value = ''
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

function goBack() {
  router.push('/admin/questions')
}
</script>

<template>
  <div class="question-import">
    <div class="page-header">
      <el-button :icon="ArrowLeft" @click="goBack">返回列表</el-button>
      <h2>批量导入题目</h2>
      <div></div>
    </div>

    <el-card>
      <el-tabs v-model="activeTab">
        <!-- CSV tab -->
        <el-tab-pane label="CSV 导入" name="csv">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 16px"
            title="CSV 格式说明"
          >
            <p style="margin:4px 0">列名（支持中英文）：<b>题目(内容/content)</b>, <b>核心点(评分指引/expected_points)</b>, <b>参考答案(reference_answer)</b>, 分类(category), 难度(difficulty)</p>
            <p style="margin:4px 0"><b>必填</b>：题目、核心点、参考答案（三个都必须有）</p>
            <p style="margin:4px 0">可选：分类(默认 basic)、难度(默认 medium)、岗位方向</p>
          </el-alert>

          <div class="csv-upload">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".csv"
              :on-change="(f: any) => handleFileUpload(f.raw as File)"
              drag
            >
              <el-icon class="el-icon--upload"><Upload /></el-icon>
              <div class="el-upload__text">
                将 CSV 文件拖到此处，或 <em>点击上传</em>
              </div>
            </el-upload>
          </div>

          <div style="margin: 12px 0">
            <span style="color: #909399; font-size: 13px">或直接粘贴 CSV 内容：</span>
            <el-button size="small" text type="primary" style="margin-left: 8px" @click="loadCsvSample">
              填入示例
            </el-button>
          </div>

          <el-input
            v-model="csvText"
            type="textarea"
            :rows="10"
            placeholder="题目,核心点,参考答案,分类,难度&#10;请解释数据库事务的ACID特性,考察对事务核心特性的理解...,事务是数据库操作的最小工作单元...,basic,medium&#10;请描述你在项目中遇到的最大挑战,考察项目经验和问题解决能力...,在上一家公司的电商项目中...,scenario,medium"
            style="font-family: monospace; font-size: 13px"
          />
        </el-tab-pane>

        <!-- JSON tab -->
        <el-tab-pane label="JSON (开发者)" name="json">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 16px"
            title="JSON 格式"
            description="适用于程序生成的数据。必填：content(题目), expected_points(核心点), reference_answer(参考答案)"
          />

          <div style="margin-bottom: 12px">
            <el-button size="small" text type="primary" @click="jsonText = jsonSample">填入示例</el-button>
          </div>

          <el-input
            v-model="jsonText"
            type="textarea"
            :rows="10"
            placeholder="在此粘贴 JSON 数组..."
            style="font-family: monospace; font-size: 13px"
          />

          <el-button type="primary" style="margin-top: 12px" @click="parseJSON" :disabled="!jsonText.trim()">
            解析预览
          </el-button>

          <div v-if="parsedItems" class="preview-section">
            <h4>预览 ({{ parsedItems.length }} 条)</h4>
            <el-table :data="parsedItems" max-height="300" stripe size="small">
              <el-table-column type="index" width="50" />
              <el-table-column prop="category" label="分类" width="100" />
              <el-table-column prop="difficulty" label="难度" width="70" />
              <el-table-column prop="content" label="内容" min-width="200" show-overflow-tooltip />
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- Import button -->
      <div style="margin-top: 16px">
        <el-button
          type="success"
          :icon="Upload"
          :loading="importing"
          size="large"
          @click="doImport"
        >
          确认导入
        </el-button>
        <span v-if="parsedItems" style="margin-left: 12px; color: #909399">
          {{ activeTab === 'json' ? parsedItems.length : '' }} 条待导入
        </span>
      </div>

      <!-- Result -->
      <div v-if="result" class="result-section">
        <el-alert
          :type="result.failed > 0 ? 'warning' : 'success'"
          :closable="false"
          :title="`导入完成: 成功 ${result.success}, 失败 ${result.failed}`"
        />
        <div v-if="result.errors.length > 0" style="margin-top: 8px">
          <p v-for="(err, i) in result.errors" :key="i" class="error-item">{{ err }}</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.question-import {
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
  flex: 1;
  text-align: center;
}

.csv-upload {
  margin-bottom: 8px;
}

.preview-section {
  margin-top: 16px;
}

.preview-section h4 {
  margin: 0 0 8px 0;
}

.result-section {
  margin-top: 16px;
}

.error-item {
  color: #f56c6c;
  font-size: 13px;
  margin: 4px 0;
}
</style>
