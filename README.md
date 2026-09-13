# InsightX · 全球跨境电商 AI 市场洞察与动态决策系统

基于 **AI 市场洞察 + Agent 决策闭环** 的出海选品与改款决策平台：将 Amazon 评论转化为痛点聚类、双栏改款工程建议与可反查的证据链。

> **P0 Minimal MVP 已闭环**：输入 ASIN → 创建任务 → Worker 领取 → LangGraph 七节点工作流（采集 → 清洗 → 向量化 → 聚类 → 双栏建议 → 证据校验 → 发布）→ Report 持久化 → SSE 实时推送 → 前端展示痛点 / 建议 / 证据。

## 技术架构

前后端分离，仅通过 HTTP 通信（REST + SSE）：

```
ai-plus/
├── frontend/    # Vue 3.5 + Vite 8 + TypeScript SPA（bun 管理依赖）
└── backend/     # FastAPI + LangGraph + PostgreSQL/pgvector（uv 管理依赖）
                  # 单包双入口：app.main（API）/ app.worker（独立 Worker 进程）
```

| 层 | 技术栈 | 说明 |
| :--- | :--- | :--- |
| 前端 | Vue 3.5 / Vite 8 / TypeScript | SPA，`EventSource` 直连后端 SSE |
| 后端 | FastAPI / Python 3.12 | REST + SSE + 任务持久化（租约 / 取消 / 重试 / 恢复） |
| AI 引擎 | LangGraph 1.2 | 7 节点 StateGraph：ingestion → normalization → embedding → clustering → proposal → evidence_validation → publish |
| 数据层 | PostgreSQL 16 + pgvector | 评论 / 片段向量（1024 维）/ 簇 / 建议 / 报告全量持久化 |

## Minimal MVP 快速开始

### 方式一：Docker（推荐）

```bash
docker compose up -d --build
# backend  → http://localhost:8000（/docs 为 OpenAPI）
# worker   → 独立进程轮询领取任务
# seed     → 写入开发预置租户 / 项目
```

### 方式二：本地开发

```bash
# 1. 数据库（或使用任意 PostgreSQL 16 + pgvector）
docker compose up -d postgres

# 2. 后端
cd backend
uv sync
uv run alembic upgrade head          # 迁移
uv run python -m app.db.seed_dev     # 预置 dev 租户/项目
uv run uvicorn app.main:app --reload --port 8000   # API
uv run python -m app.worker          # Worker（另一个终端）

# 3. 前端
cd frontend
bun install
bun run dev        # http://localhost:5173，/api 自动代理到 :8000
```

### Demo 演示

1. 打开前端，进入「诊断流程」
2. 输入演示 ASIN：**B08N5WRWNW**，点击「执行流程」
3. 页面实时展示 7 个节点的执行状态与进度（来自后端 SSE）
4. 完成后查看 Dashboard / VOC 聚类 / 双栏建议，点击证据可查看真实评论原文
5. 刷新页面：已完成任务仍可从后端查询

## 数据模式（诚实标注）

| 模式 | 配置 | 行为 |
| :--- | :--- | :--- |
| Demo（默认） | `AMAZON_PROVIDER=demo`、`EMBEDDING_PROVIDER=deterministic` | 读取内置演示数据集 `backend/app/demo_data/B08N5WRWNW.json`（104 条人工合成评论）；向量化使用确定性测试向量。报告 `source_mode=DEMO_DATASET`，前端展示 Demo Dataset 横幅 |
| Real | `AMAZON_PROVIDER=http` + `AMAZON_API_BASE_URL` + `AMAZON_API_KEY` | 调用真实 Amazon 采集 API；凭证缺失时 fail-fast，禁止自动回退 demo |
| bge-m3 | `EMBEDDING_PROVIDER=bge_m3` + `uv sync --extra embedding` | 加载 BAAI/bge-m3 生成 1024 维真实向量（演示数据集模式同样适用） |

生产环境（`APP_ENV=prod`）拒绝预置身份与演示数据集。

## 环境变量（backend/.env）

| 变量 | 默认 | 说明 |
| :--- | :--- | :--- |
| `APP_ENV` | `dev` | `prod` 禁用预置身份与 demo provider |
| `DATABASE_URL` | 本地 insightx 库 | asyncpg URL |
| `AMAZON_PROVIDER` | `demo` | `demo` / `http` |
| `AMAZON_API_BASE_URL` / `AMAZON_API_KEY` | 空 | http 模式必填 |
| `EMBEDDING_PROVIDER` | `deterministic` | `deterministic` / `bge_m3` |
| `ANTHROPIC_API_KEY` | 空 | 配置后建议生成启用 LLM 增强（可选） |

## 常用命令

```bash
# 后端测试（DB 集成测试需 PostgreSQL，可用 TEST_DATABASE_URL 指向隔离库）
cd backend && uv sync --frozen && uv run pytest -q

# 前端构建（含 vue-tsc 类型检查）
cd frontend && bun install && bun run build

# 聚类阈值校准（离线，开发工具）
cd backend && uv run python scripts/calibrate_clustering.py

# 手动全链路验证（开发工具）
cd backend && uv run python scripts/manual_pipeline_run.py
```

## P0 范围说明

P0 已实现：七节点 LangGraph 工作流、Top 5 痛点聚类（余弦阈值法 + 确定性严重度）、双栏改款建议（规则引擎，LLM 可选）、证据绑定与反查（防幻觉门：引用不存在的评论将阻止发布）、Report 持久化与 API、SSE 实时事件、任务租约 / 取消 / 重试 / 恢复。

P1 未实现（页面如有入口均为 Demo 标注）：Claude Vision 图片取证、财务否决（回本周期 / FBA 节约额在报告中如实标注 NOT_EVALUATED）。P2 未实现：历史回测、TikTok / Temu 跨平台、Alerts、供应链信号。

## 文档

- [技术方案](docs/技术方案.md) — 模型选型、Agent 工作流与数据管道
- [PRD](docs/PRD.md) — 产品需求与里程碑
- [API 接口文档](docs/api.md) — REST + SSE 契约（前后端并行开发依据）
