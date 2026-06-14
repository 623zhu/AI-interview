# AI-Interview

基于 LLM 智能体的 AI 模拟面试平台。系统通过 ReAct Agent 驱动面试对话，结合 RAG 语义检索题目、实时评分画像构建，为候选人提供接近真实的面试体验。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + TypeScript + Element Plus)                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ SSE / REST
┌────────────────────────▼────────────────────────────────────────┐
│  Backend (FastAPI)                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ Interview    │  │ Resume Parse │  │ Score/Report Agent    │ │
│  │ Agent (ReAct)│  │ Agent        │  │                       │ │
│  └──────┬───────┘  └──────────────┘  └───────────────────────┘ │
│         │                                                       │
│  ┌──────▼───────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │ LangGraph    │  │ RAG Module   │  │ Reranker              │ │
│  │ (ReAct Loop) │  │ (Chroma)     │  │ (BGE-reranker-v2-m3) │ │
│  └──────────────┘  └──────────────┘  └───────────────────────┘ │
└────────────────────────┬────────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
│ MySQL 8.0   │  │ Redis 7     │  │ Chroma (Vector) │
│ (持久存储)   │  │ (画像缓存)   │  │ (语义检索)      │
└─────────────┘  └─────────────┘  └─────────────────┘
```

## 核心智能体

### 1. Interview Agent (面试智能体)

基于 **LangGraph ReAct** 范式构建的面试官智能体，是系统的核心组件。

**工作流程：**

1. 从 Redis 加载候选人画像（技能评估、整体印象）
2. 组装上下文：岗位技能树 + 简历摘要 + 对话历史 + 当前画像
3. 进入 ReAct 循环，通过 Tool Calling 驱动面试
4. 逐 token 通过 SSE 流式推送至前端
5. 每轮结束后将更新的画像持久化到 Redis（TTL 24h）

**可用工具（Tools）：**

| 工具 | 功能 |
|------|------|
| `evaluate_answer` | 评估候选人回答：打分（confidence/depth）+ 评语 + 更新画像 |
| `retrieve_questions` | 语义检索题目池，返回 3-5 道候选题（自动去重已问题目） |
| `update_profile` | 直接调整画像（无需详细评语） |
| `end_interview` | 结束面试，触发报告生成 |

**设计特点：**
- 画像跨轮次累积：通过 Redis 持久化 `CandidateProfile`，面试过程中逐步构建候选人技能图谱
- 技能树引导：基于岗位 `skill_tree`（层级 JSON）引导面试方向
- 自适应追问：根据回答质量决定深入追问或切换方向
- SSE 流式输出：实时 token 推送，前端逐字展示

### 2. Resume Parse Agent (简历解析智能体)

基于 LLM 的结构化信息提取，将非结构化简历文本转为标准 JSON。

- 支持 PDF / DOCX 格式上传
- 提取：个人信息、技能、工作经历、项目经历、教育背景等
- 严格约束：不编造信息，无信息则填 null

### 3. Score/Report Agent (评分报告智能体)

面试结束后，基于完整对话记录和各题评分生成结构化面试报告。

## RAG 语义检索

面试题目的检索采用两阶段 Retrieve-Rerank 架构：

```
用户意图（Agent决策）
    │
    ▼ Embedding (Ollama + bge-m3, dim=1024)
    │
    ▼ Vector Search (Chroma, top-k=20)
    │
    ▼ Cross-Encoder Rerank (BAAI/bge-reranker-v2-m3)
    │
    ▼ 返回 Top 3-5 候选题目
```

- 题目入库时按 `category | job_category | difficulty | content` 拼接为嵌入文本
- 支持按分类/难度进行预过滤
- Reranker 为可选组件，缺失时降级为纯向量 top-k

## 技术栈

### 后端

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.115 + Uvicorn (全异步) |
| Agent 框架 | LangGraph 0.2 + LangChain 0.3 |
| LLM | DeepSeek (OpenAI 兼容接口) |
| 向量嵌入 | Ollama + bge-m3 (1024 维) |
| 重排序 | FlagEmbedding / bge-reranker-v2-m3 |
| 向量数据库 | Chroma 0.5 |
| 关系数据库 | MySQL 8.0 + SQLAlchemy (async) |
| 缓存 | Redis 7 |
| 认证 | JWT + bcrypt |
| 文件解析 | PyPDF2 + pdfplumber + python-docx |

### 前端

| 层级 | 技术 |
|------|------|
| 框架 | Vue 3 + TypeScript |
| 构建工具 | Vite 5 |
| UI 组件库 | Element Plus |
| 状态管理 | Pinia |
| 图表 | ECharts 5 |
| 通信 | Axios + SSE (EventSource) |

## 数据模型

核心实体关系：

```
User ──┬── Resume ──── ResumeJobMatch ──── JobPosition
       │                                       │
       └── InterviewSession ──────────────────┘
               │
               ├── InterviewMessage (对话记录)
               ├── InterviewQuestionLink (已问题目)
               └── ScoreReport (面试报告)
```

`JobPosition.skill_tree` 示例：
```json
{
  "domains": [
    {
      "name": "后端开发",
      "weight": 0.4,
      "skills": [
        {
          "name": "Python",
          "level": "senior",
          "children": [
            { "name": "异步编程" },
            { "name": "类型系统" }
          ]
        }
      ]
    }
  ]
}
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- MySQL 8.0
- Redis 7
- Ollama（运行 bge-m3 嵌入模型）

### 1. 启动基础设施

```bash
cd backend
docker-compose up -d  # MySQL + Redis
```

### 2. 启动 Ollama 嵌入服务

```bash
ollama pull bge-m3
ollama serve
```

### 3. 后端

```bash
cd backend
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env  # 填写 DEEPSEEK_API_KEY 等

# 数据库迁移
alembic upgrade head

# 启动服务
python main.py
```

### 4. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 开始使用。

## API 概览

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `/api/v1/auth/*` | 注册、登录、Token 刷新 |
| 简历 | `/api/v1/resumes/*` | 上传、解析、列表 |
| 岗位 | `/api/v1/jobs/*` | 岗位列表与搜索 |
| 面试 | `/api/v1/interviews/*` | 创建/开始/对话(SSE)/结束 |
| 题库 | `/api/v1/questions/*` | 题目管理（管理员） |
| 报告 | `/api/v1/reports/*` | 面试报告查看 |
| 看板 | `/api/v1/dashboard/*` | 数据统计 |

**面试对话接口**（SSE 事件流）：

```
POST /api/v1/interviews/{session_id}/chat

SSE Events:
  status    → 处理状态
  action    → Agent 工具调用
  score     → 评分结果
  profile   → 画像更新
  token     → 逐字流式输出
  question  → 下一个问题（含元数据）
  done      → 面试结束
```

## 项目结构

```
backend/
├── app/
│   ├── agent/          # 智能体核心
│   │   ├── interview_agent.py   # 面试智能体（ReAct 主循环）
│   │   ├── tools.py             # Agent 工具定义
│   │   ├── rag.py               # RAG 语义检索
│   │   ├── parse_agent.py       # 简历解析智能体
│   │   ├── score_agent.py       # 评分报告智能体
│   │   └── prompts.py           # 系统提示词
│   ├── api/v1/         # REST API 路由
│   ├── core/           # 基础设施
│   │   ├── llm.py               # LLM 客户端（DeepSeek）
│   │   ├── embedding.py         # 嵌入模型（Ollama）
│   │   ├── reranker.py          # 重排序模型
│   │   ├── chroma.py            # 向量数据库
│   │   ├── database.py          # MySQL 连接
│   │   └── config.py            # 全局配置
│   ├── models/         # SQLAlchemy ORM 模型
│   ├── schemas/        # Pydantic 请求/响应 Schema
│   └── services/       # 业务逻辑层
├── alembic/            # 数据库迁移
├── eval/               # RAG 评估工具
├── docker-compose.yml
└── requirements.txt
```

## License

MIT
