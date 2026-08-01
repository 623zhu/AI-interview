# AI Interview

AI Interview 是一个面向技术岗位的智能面试系统。候选人可以上传简历、选择目标岗位并参加 AI 面试；系统会根据岗位技能树、简历经历、题库检索结果和当前对话状态动态决定下一步提问，并在面试结束后生成结构化评分与改进建议。

项目包含候选人端、管理端、FastAPI 后端、LangGraph 面试引擎、MySQL 业务数据、Redis 运行状态、Chroma 向量索引和本地 RAG 评测工具。


## 项目展示

### 选择面试岗位

候选人完成简历解析后，可以选择目标岗位并查看岗位对应的技术标签。

![候选人选择面试岗位](images/select-job.png)

### AI 实时面试

面试室展示当前进度、已用时间和完整问答记录，支持提交回答、跳过问题和主动结束面试。

![AI 实时面试界面](images/interview-room.png)

### 面试报告

面试完成后保留完整问答记录，并展示逐轮分析、评分依据和改进反馈。

![面试报告与逐轮分析](images/interview-report.png)

### 题库管理

管理端支持题目搜索、分类与难度筛选、新增、批量导入、启停及向量库同步。

![管理端题库管理](images/admin-dashboard.png)

### 岗位与技能树管理

岗位配置包含岗位描述、技术标签、技能权重、多级技能节点及节点难度，用于驱动面试覆盖和报告聚合。

![管理端岗位与技能树配置](images/job-management.png)

## 核心功能

### 候选人端

- 使用邮箱注册和登录，支持访问令牌自动刷新。
- 上传 PDF、DOC 或 DOCX 简历，提取文本并生成结构化摘要。
- 浏览岗位要求，选择简历和岗位创建面试。
- 配置最大轮数和最长面试时间。
- 通过流式事件接收 AI 提问、阶段变化和报告状态。
- 支持回答、跳过当前问题、主动结束面试。
- 查看总分、技能得分、优势、不足和改进建议。

### AI 面试引擎

- 根据岗位技能树计算当前应覆盖的技能范围。
- 根据目标岗位和简历摘要生成与岗位相关的自我介绍开场题。
- 结合简历摘要、岗位快照和历史问答，对题库候选题进行受约束改写或生成下一问。
- 支持澄清、追问、能力衔接、技能切换和结束五类决策。
- 使用 RAG 从题库检索与目标技能匹配的问题。
- 独立评估每轮回答，不让评分结果干扰后续提问。
- 面试完成后按岗位技能权重聚合成绩并生成报告。
- 使用事件编号和问题编号处理重复请求与过期页面提交。

### 管理端

- 查看和维护用户信息。
- 创建、编辑和删除岗位及其技能要求。
- 管理题库、题目难度、技能标签和参考要点。
- 查看面试会话、面试状态和生成的报告。
- 通过统计面板了解系统中的用户、岗位、面试和报告数据。

## 系统架构

```text
Candidate Web (Vue 3)          Admin Web (Vue 3)
          |                           |
          +------------ HTTP / SSE --+
                                      |
                              FastAPI Application
                         /             |             \
                 Auth & CRUD     Interview Service    Admin API
                                      |
                 +---------------+----------------+---------------+
                 |               |                |               |
          LangGraph Runtime   MySQL 8          Redis 8         Chroma
       Main / Evaluation /    Business Data    Checkpoints     Vector Index
              Report              |                |               |
                 +----------------+----------------+---------------+
                                      |
                       DeepSeek / Ollama / Reranker
```

后端将业务记录和面试运行状态分开保存：

| 数据 | 存储位置 |
| --- | --- |
| 用户、简历、岗位、题库 | MySQL |
| 面试会话目录与状态 | MySQL |
| 当前问题、原始回答、技能覆盖、已用题目 | Redis LangGraph Checkpointer |
| 单轮评估结果 | Evaluation Graph 独立 Checkpoint |
| 完整面试归档与最终报告 | MySQL |

## 面试工作流

系统没有把面试实现成固定题目列表，而是由三个相互独立的 LangGraph 图共同完成：

1. **Interview Graph** 负责实时面试、下一问决策和状态推进。
2. **Evaluation Graph** 负责在后台评价已经完成的回答。
3. **Report Graph** 负责补齐评估、聚合分数并生成最终报告。

这种拆分保证实时提问不会等待评分，同时避免模型根据评分刻意降低或提高下一题难度。

### 1. 创建与启动面试

候选人创建面试时提交：

- `resume_id`：本次面试使用的简历。
- `job_id`：目标岗位。
- `max_turns`：最大问答轮数。
- `max_duration_minutes`：最长面试时间。

后端会校验简历归属、岗位状态和配置范围，然后创建 `created` 状态的会话。启动面试后，系统完成以下准备工作：

1. 读取简历结构化摘要。
2. 固化岗位名称、描述、技能树和技能权重，形成岗位快照。
3. 初始化技能覆盖情况、已使用题目集合和事件集合。
4. Interview Graph 调用模型，根据岗位和简历生成自我介绍开场题。
5. 将会话状态改为 `in_progress`，并通过 Redis Checkpointer 保存运行状态。

会话状态流转如下：

```mermaid
stateDiagram-v2
    [*] --> created: 创建会话
    created --> in_progress: 启动面试
    in_progress --> in_progress: 回答或跳过
    in_progress --> completed: 主动结束或达到停止条件
    created --> [*]: 删除记录
    in_progress --> [*]: 删除记录
    completed --> [*]: 删除记录
```

### 2. 实时面试主图

主图每收到一次候选人事件，就记录当前回答并判断下一步动作。图会在等待回答时暂停，收到回答、跳过或结束事件后从同一 Checkpoint 恢复。

```mermaid
flowchart TD
    A[initialize] --> A1[compose_opening_question]
    A1 --> B[wait_for_candidate]
    B -->|回答或跳过| C[record_turn]
    B -->|重复或过期事件| D[ignore_event]
    D --> B
    B -->|主动结束| K[finalize]
    C --> E[check_limits]
    E -->|达到轮数、时间或覆盖条件| K
    E -->|继续| F[prepare_frontier]
    F --> G[interviewer_decision]
    G --> H[validate_decision]
    H -->|SWITCH 或策略重定向| I[retrieve_question_pool]
    I --> J{存在候选题}
    J -->|是| N[按上下文改写题库题]
    J -->|否| O[按目标技能生成新题]
    N --> P[保留原题 ID 与快照]
    P --> L[present_question]
    O --> L
    H -->|CLARIFY / PROBE / BRIDGE| L
    H -->|FINISH| K
    L --> B
    K --> M[completed]
```

主图允许模型选择以下动作：

| 动作 | 使用场景 | 下一问来源 |
| --- | --- | --- |
| `CLARIFY` | 回答存在歧义、概念不清或需要候选人重新表述 | 围绕当前回答生成澄清问题 |
| `PROBE` | 当前技能仍有深入考察价值 | 围绕证据、原理、取舍或实现细节追问 |
| `BRIDGE` | 从当前话题自然过渡到相关技能 | 使用当前回答作为衔接点生成问题 |
| `SWITCH` | 当前技能已覆盖或需要切换考察方向 | 检索题库并按上下文改写；无候选题时按目标技能生成 |
| `FINISH` | 达到轮数、时间或技能覆盖要求 | 结束面试并进入报告流程 |

模型的输出必须通过结构化校验。技能路径必须存在于岗位技能树中，题目长度、目标技能、引用题号和动作组合也必须符合规则。追问次数达到上限或模型动作不符合策略时，后端会将它重定向为正常的 `SWITCH` 并继续执行 RAG，不会进入 fallback。

面试主图只有一种 fallback：开场出题、决策、题库题改写或空题库出题的模型调用经过配置的重试后仍然抛出异常，才使用确定性问题保证会话可以继续。题库题改写失败时会使用原题，空题库本身不是故障，会先执行正常的模型出题流程。

### 3. 技能覆盖与下一问决策

岗位配置以技能树表示，例如：

```text
后端开发
├── Python
│   ├── 语言基础
│   └── 异步编程
├── Web 框架
│   ├── FastAPI
│   └── 接口设计
└── 数据存储
    ├── MySQL
    └── Redis
```

每轮回答后，系统更新对应技能的覆盖次数，并结合以下信息生成技能候选集合：

- 岗位要求的技能权重。
- 已覆盖和未覆盖的技能节点。
- 当前正在讨论的技能。
- 简历中出现的技术和项目经历。
- 已经使用过的题目及历史追问。
- 剩余轮数和剩余时间。

技能树决定可以考察哪些内容以及下一步可选择的技能，但不会强制按固定顺序提问。候选人跳过问题时只记录跳过，不将该技能视为已经有效覆盖。

### 4. 题库 RAG 检索

当主图选择 `SWITCH` 时，后端优先按目标技能查询题库：

```mermaid
flowchart LR
    A[目标技能与岗位上下文] --> B[生成检索查询]
    B --> C[向量召回]
    C --> D[技能、难度和启用状态过滤]
    D --> E[Reranker 重排]
    E --> F[排除已使用题目]
    F --> G{候选题池是否为空}
    G -->|否| H[选择排序第一的题目]
    H --> J[结合本轮上下文受约束改写]
    J --> K[展示改写题并保留原题关联]
    G -->|是| I[模型按目标技能生成新题]
```

检索时综合岗位描述、目标技能、简历摘要和当前面试上下文。题库记录保留技能标签、难度、标准要点等结构化信息，便于筛选和后续评价。已使用题目会被排除，防止同一会话重复提问。

命中题库后，模型可以结合候选人刚才的回答和项目经历调整题目表述，但不能改变目标技能、难度和考察要点，也不能向候选人透露评分标准或参考答案。运行状态会保留原题 ID 和原题快照，候选人接口展示改写后的题目且不返回原题快照；Evaluation Graph 仍通过原题 ID 读取题库中的参考要点与评分标准，因此改写不会切断评分依据和审计关联。

候选池为空时，系统以目标技能和最近问答为约束调用出题模型，动作仍保持 `SWITCH`、来源标记为 `generated`。

项目还提供独立的 RAG 评测入口，可计算 `Recall@K`、`MRR`、`NDCG@K`、`Hit Rate` 和延迟指标，用于比较召回与重排配置。

### 5. 请求幂等与页面恢复

回答请求可以携带：

- `event_id`：客户端事件的唯一编号。
- `expected_question_id`：客户端认为自己正在回答的问题编号。

后端将已经处理的事件编号写入运行状态。相同 `event_id` 再次提交时不会重复记一轮；如果 `expected_question_id` 与当前问题不一致，说明页面状态已经过期，请求会被忽略并返回最新面试状态。

因此刷新页面、网络重试或浏览器重复提交不会轻易造成重复回答和重复出题。

### 6. 单轮回答评估

主图返回下一问后，上一轮回答会进入独立的 Evaluation Graph。它使用单独的线程编号 `eval:{session_id}:{turn_id}`，不会把评分传回实时面试图。

评估内容包括：

| 字段 | 含义 |
| --- | --- |
| `correctness` | 技术结论是否正确 |
| `completeness` | 是否覆盖关键要点 |
| `depth` | 是否体现原理、实践和取舍 |
| `communication` | 表达是否清晰、有结构 |
| `covered_points` | 已覆盖的参考要点 |
| `missed_points` | 未覆盖或错误的要点 |
| `evidence` | 支撑评分的候选人原话或事实 |
| `score_confidence` | 当前评分的可信度 |

开场介绍不计入技术总分，但 Evaluation Graph 仍会根据实际回答生成针对性的文字反馈，不再使用固定评语。评估失败不会中断面试，失败的轮次会在生成最终报告时重试；最终仍无法评价的轮次会明确标记为评价不可用且不计分，其余轮次继续生成报告，不会因为单轮模型失败丢失整份报告。

### 7. 结束条件

发生以下任一情况时，主图可以结束面试：

- 候选人主动调用结束接口。
- 已达到配置的最大问答轮数。
- 已达到配置的最长面试时间。
- 岗位核心技能已得到足够覆盖。
- 面试图生成合法的 `FINISH` 决策。

结束时，后端将完整终态写入面试归档，并把会话标记为 `completed`。报告可以通过同步接口生成，也可以由 FastAPI 后台任务生成。

### 8. 报告生成图

```mermaid
flowchart TD
    A[load_completed_session] --> B[collect_turn_evaluations]
    B --> C{存在缺失评估?}
    C -->|是| D[retry_missing_evaluations]
    D --> E[aggregate_skill_scores]
    C -->|否| E
    E --> F[apply_job_skill_weights]
    F --> G[generate_report_narrative]
    G --> H[persist_score_report]
```

报告生成分为两类计算：

1. **确定性评分**：先计算各技能下有效回答的平均分，再应用岗位快照中的技能权重得到总分。围绕同一技能的连续追问不会重复放大该技能权重。
2. **文字总结**：模型根据评分证据生成总结、优势、不足和改进建议，但不能修改后端已经计算出的总分。

最终报告包含：

- 总分和各技能得分。
- 每轮回答的评分与评语。
- 已覆盖和遗漏的知识点。
- 候选人的主要优势与不足。
- 可执行的学习和面试改进建议。

### 9. 状态保存与故障恢复

实时面试优先从 Redis 恢复 LangGraph Checkpoint。完成面试后，系统会把完整终态保存到 MySQL 归档；如果 Redis 状态过期，报告生成仍可以从 MySQL 终态归档恢复。

Redis Checkpoint 默认保留 7 天，读取活跃会话时会刷新有效期。服务启动后还会扫描已经完成但尚未生成报告的会话，并重新提交报告任务。

Redis 连接使用异步 Checkpointer；生产部署建议启用 AOF `everysec`。会话写操作通过带自动续期的 Redis 锁串行化，并使用 Lua 脚本确认锁所有者后释放，避免并发回答互相覆盖。

### 10. 前端流式反馈

面试接口通过 SSE 将执行进度发送给候选人端。前端可以按事件类型更新当前问题、加载状态和报告状态，常见事件包括：

- 面试已启动。
- 候选人回答已接收。
- 正在决定下一步动作。
- 正在检索题库。
- 新问题已生成。
- 面试已完成。
- 报告生成中或已完成。
- 请求被判定为重复或过期。

候选人主动结束面试后，报告页会在报告生成期间自动刷新状态。逐题报告只收录已经回答的轮次；结束时尚未回答的当前问题不会被当作有效问答写入报告。

完整的一次面试请求链路如下：

```mermaid
sequenceDiagram
    participant U as 候选人端
    participant API as FastAPI
    participant IG as Interview Graph
    participant R as Redis
    participant EG as Evaluation Graph
    participant DB as MySQL
    participant RG as Report Graph

    U->>API: 创建并启动面试
    API->>DB: 读取简历和岗位，创建会话
    API->>IG: 初始化岗位快照与技能覆盖
    IG->>IG: 模型生成岗位相关开场题
    IG->>R: 保存 Checkpoint
    IG-->>U: SSE 返回开场问题

    loop 每轮问答
        U->>API: 回答 + event_id + expected_question_id
        API->>IG: 恢复状态并记录回答
        IG->>IG: 检查停止条件并决定动作
        IG->>IG: 必要时检索题库并改写或生成下一问
        IG->>R: 保存最新 Checkpoint
        IG-->>U: SSE 返回下一问
        API->>EG: 异步评估上一轮回答
        EG->>R: 保存单轮评估
    end

    IG->>DB: 保存完整终态归档
    API->>RG: 提交报告任务
    RG->>R: 收集或补齐单轮评估
    RG->>DB: 保存结构化评分报告
    API-->>U: 返回最终报告
```

## 技术栈

### 后端

- Python 3.11+
- FastAPI、Uvicorn
- SQLAlchemy 2、Alembic、PyMySQL
- LangGraph、LangChain
- Redis、Chroma
- Pydantic 2
- Python JOSE、bcrypt
- Pytest

### 前端

- Vue 3、TypeScript
- Vite
- Pinia
- Vue Router
- Element Plus
- Axios
- ECharts
- Element Plus Icons

### 模型与检索

- DeepSeek 兼容接口：对话、决策、评估和报告文字生成。
- Ollama：本地 Embedding 和 Reranker 服务。
- Chroma：题库向量索引与相似度召回。
- FlagEmbedding：可选的本地 Cross-Encoder 重排；加载失败时回退到向量排序。

## 数据模型

| 表 | 用途 |
| --- | --- |
| `users` | 用户账号、角色和状态 |
| `refresh_tokens` | 刷新令牌与撤销状态 |
| `resumes` | 简历文件、提取文本和结构化摘要 |
| `jobs` | 岗位描述、技能树和技能权重 |
| `questions` | 题目、技能标签、难度和参考要点 |
| `interview_sessions` | 面试目录、配置和会话状态 |
| `interview_messages` | 兼容早期会话的历史消息 |
| `interview_archives` | 已完成面试的完整终态快照 |
| `score_reports` | 总分、技能评分和报告内容 |
| `embedding_cache` | 文本向量缓存 |

面试的逐轮运行状态保存在 Redis Checkpoint 中，面试完成后一次性归档到 `interview_archives`。`interview_messages` 
## 项目结构

```text
AI_interview/
├── backend/
│   ├── alembic/            # 数据库迁移
│   ├── app/
│   │   ├── agent/          # 三张 LangGraph 图及结构化协议
│   │   ├── api/            # 用户端和管理端接口
│   │   ├── core/           # 配置、安全、状态和异常处理
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── repositories/   # 数据访问层
│   │   ├── schemas/        # Pydantic 请求与响应模型
│   │   ├── services/       # 业务服务
│   │   └── utils/          # 简历处理等通用工具
│   ├── eval/rag/           # RAG 离线评测
│   ├── scripts/            # 数据导入与维护脚本
│   └── tests/              # 后端测试
├── frontend/
│   ├── user/               # 候选人端入口与组件
│   ├── admin/              # 管理端入口与组件
│   ├── shared/             # 两端共享代码
│   └── src/                # 页面、路由、状态与接口封装
├── docker-compose.yml      # MySQL 和 Redis
└── README.md
```

## 本地运行

### 环境要求

- Python 3.11+
- Node.js 22.12+
- Docker Desktop
- Ollama
- 可访问的 DeepSeek 兼容 API

### 1. 配置并启动基础服务

```powershell
Copy-Item .env.example .env
docker compose up -d mysql redis
```

默认端口：

| 服务 | 地址 |
| --- | --- |
| MySQL | `127.0.0.1:3307` |
| Redis | `127.0.0.1:6381` |

### 2. 准备本地 Embedding 服务

```powershell
ollama pull bge-m3
ollama serve
```

Ollama 默认监听 `127.0.0.1:11434`。Reranker 由 `FlagEmbedding` 在首次使用时加载配置的模型。

### 3. 配置并启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `backend/.env`，至少设置以下变量：

```dotenv
DATABASE_URL=mysql+aiomysql://aiiv2:aiiv2_dev_password@127.0.0.1:3307/ai_interview?charset=utf8mb4
DATABASE_URL_SYNC=mysql+pymysql://aiiv2:aiiv2_dev_password@127.0.0.1:3307/ai_interview?charset=utf8mb4
REDIS_URL=redis://127.0.0.1:6381/0
JWT_SECRET_KEY=replace-with-at-least-32-random-characters
SECRET_KEY=replace-with-another-32-character-random-secret
VERIFICATION_HMAC_SECRET=replace-with-another-32-character-random-secret
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
```

初始化数据库并启动接口：

```powershell
alembic upgrade head
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

接口启动后可访问：

- API：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/health`

### 4. 启动候选人端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

### 5. 启动管理端

```powershell
cd frontend
npm run dev:admin
```

默认地址：`http://127.0.0.1:5174`

## 测试与构建

运行后端测试：

```powershell
cd backend
pytest -q
```

构建候选人端：

```powershell
cd frontend
npm run build
```

构建管理端：

```powershell
cd frontend
npm run build:admin
```

运行 RAG 评测：

```powershell
cd backend
python -m eval.rag.run_eval run --label baseline --no-rerank
```

## 主要接口

### 认证与个人资料

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/profile`

### 简历与岗位

- `GET /api/v1/resumes`
- `POST /api/v1/resumes`
- `DELETE /api/v1/resumes/{resume_id}`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`

### 面试与报告

- `POST /api/v1/interviews`
- `POST /api/v1/interviews/{session_id}/start`
- `POST /api/v1/interviews/{session_id}/chat`
- `POST /api/v1/interviews/{session_id}/skip`
- `POST /api/v1/interviews/{session_id}/end`
- `GET /api/v1/interviews/{session_id}`
- `GET /api/v1/interviews/{session_id}/report`

### 管理端

- `/api/v1/admin/users`
- `/api/v1/admin/jobs`
- `/api/v1/admin/questions`
- `/api/v1/admin/interviews`
- `/api/v1/admin/reports`
