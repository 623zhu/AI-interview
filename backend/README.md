# AI-Interview Backend

后端是基于 FastAPI、SQLAlchemy Async 和 LangGraph 的完整应用，正式入口为 `backend/main.py`。

## 能力

- 注册、登录、JWT 轮换、黑名单和 Redis 限流。
- 简历上传、解析、鉴权下载、重新解析和删除。
- 岗位、题库、用户和看板管理。
- 实时面试 Command Graph、独立 Evaluation Graph 和 Report Graph。
- Redis checkpoint、会话锁、MySQL 面试归档与报告恢复。
- Chroma 检索、Ollama embedding 和可选本地 reranker。
- Request ID、结构化日志、存活与就绪检查。

## 目录职责

```text
app/api/v1/       HTTP 路由、鉴权和所有权校验
app/agent/        LangGraph 工作流、策略、RAG 和提示词
app/core/         配置、数据库、Redis、LLM、检索、日志
app/models/       SQLAlchemy 模型
app/repositories/ 当前主要用于认证数据访问
app/schemas/      Pydantic 请求与响应模型
app/services/     认证、面试会话、归档和报告服务
alembic/          正式数据库迁移
eval/rag/         RAG 离线评测
scripts/          本地维护脚本
tests/            单元、API、并发和工作流测试
```

当前代码并非所有模块都采用同一种分层：认证链路按 repository/service 分层，部分业务 API 仍直接执行 SQLAlchemy 查询。修改时应遵循相邻代码的实际边界，不要在未迁移的模块中制造半套抽象。

## 配置

从 `.env.example` 创建 `.env`。关键配置：

```env
DATABASE_URL=mysql+aiomysql://...@127.0.0.1:3307/ai_interview?charset=utf8mb4
DATABASE_URL_SYNC=mysql+pymysql://...@127.0.0.1:3307/ai_interview?charset=utf8mb4
REDIS_URL=redis://127.0.0.1:6381/0
LANGGRAPH_CHECKPOINTER_BACKEND=redis
CHROMA_PERSIST_DIR=./chroma_data
DEEPSEEK_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=bge-m3
```

生产环境还必须配置强随机 `SECRET_KEY`、`JWT_SECRET_KEY`、`VERIFICATION_HMAC_SECRET`、SMTP 凭据和明确的 CORS origin。

## 初始化与启动

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python manage.py seed-jobs
python manage.py sync-questions
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

接口：

- OpenAPI：`http://127.0.0.1:8000/docs`
- 存活：`GET /health`
- 就绪：`GET /ready`
- 业务前缀：`/api/v1`

## 管理命令

```powershell
python manage.py create-admin -u admin -e admin@example.com -p your-password
python manage.py seed-jobs
python manage.py sync-questions
```

## 测试

```powershell
python -m pytest -p no:cacheprovider
```

当前基线覆盖认证、权限、简历安全、面试生命周期、并发锁、归档、报告、RAG 异步调用、LLM 可靠性、健康检查和结构化日志。

## 数据约束

- 正式 schema 只由 Alembic 管理，当前 head 为 `003`。
- Redis 是 checkpoint 和临时状态存储，不是业务历史的唯一来源。
- 完成的面试必须写入 `interview_archives`，避免 checkpoint TTL 到期后历史丢失。
- 岗位删除已有服务端引用保护；简历删除当前仍会通过外键级联删除关联面试和报告，只能在确认未引用后执行。
- 报告恢复当前由应用生命周期中的进程内任务执行，Celery 仍是后续迁移方案。
