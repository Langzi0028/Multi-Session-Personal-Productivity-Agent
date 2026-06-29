# 多 Session 个人效率 Agent：后端框架确认与 Issues 拆解

本文档基于 `开发文档.md` 分析整理，用于后续 vibe-coding / agent 开发时作为 issue 拆解与实现顺序参考。

> 2026-06-28 变更说明：用户已明确要求当前项目改为 LangGraph 实现，包括图节点、工具调用、`@tool` 工具和记忆机制。因此早期“不依赖 LangGraph”的约束已被当前用户指令覆盖；当前实现以 LangGraph-backed Runtime 为准。

---

## 1. 当前项目事实

- 当前目录：`D:\PythonProject\bishi`
- 当前目录尚无实际 Python 后端源码、测试、`requirements.txt` 或应用骨架。
- 当前主要输入文档为：`开发文档.md`
- 项目应按“从零实现后端 MVP”处理。
- 开发文档明确要求：主流程从零实现最小 Agent Runtime，不依赖 LangGraph、OpenHands、OpenClaw 等现成 Agent 框架。

---

## 2. 后端项目框架确认

### 2.1 MVP 技术栈

建议固定为：

```text
Python
FastAPI
Pydantic
SQLite
OpenAI-compatible API
pytest
```

配套实现：

```text
手写 Agent Runtime Loop
手写 Tool Registry
手写 Action Parser
FakeLLM / ScriptedLLM 测试客户端
SQLite 短期记忆 / todo / trace / async_jobs
长期记忆接口与 mock / 轻量检索实现
```

### 2.2 运行形态

建议采用“双入口”：

1. **FastAPI 主 API 服务**

   ```text
   uvicorn app.main:app --reload
   ```

   FastAPI 负责 HTTP API、请求响应 DTO、调用 Runtime。

2. **CLI Demo / 调试入口**

   ```text
   python -m app.main
   ```

   CLI 仅用于录屏演示和本地调试，必须复用同一套 runtime，不应另写一套业务逻辑。

### 2.3 不纳入 MVP 的内容

以下内容可作为后续扩展，不建议放入 MVP：

```text
PostgreSQL
Redis
Celery / RabbitMQ
pgvector / Milvus
React / Vue 前端
OpenTelemetry
复杂权限系统
复杂 Multi-Agent 调度
Scheduler / Reminder 定时任务
真实 Chroma / FAISS 强依赖
```

---

## 3. 必须先固定的合同边界

实现前应先冻结以下 Draft 合同，避免后续接口、数据结构、测试和 demo 漂移。

### 3.1 API 合同

建议最小 API：

```text
POST /sessions
GET  /sessions/{session_id}
POST /sessions/{session_id}/messages
GET  /sessions/{session_id}/todos
GET  /sessions/{session_id}/trace
GET  /async-jobs/{job_id}
POST /async-jobs/{job_id}/complete   # mock / 测试场景可用
```

关键规则：

- 请求必须明确 `user_id`。
- session 级数据必须使用 `user_id + session_id` 作为隔离边界。
- API 响应应明确是否返回：
  - `session_id`
  - `session_status`
  - `answer`
  - `trace_id`
  - `tool_calls`
  - `error_code`

### 3.2 LLM 输出协议合同

只允许两类输出：

```json
{
  "type": "final",
  "thought_summary": "简短决策摘要",
  "answer": "最终回复"
}
```

```json
{
  "type": "tool_call",
  "thought_summary": "简短决策摘要",
  "tool_name": "weather",
  "arguments": {
    "city": "北京"
  }
}
```

注意：

- 不应保存完整 chain-of-thought。
- 原文中的 `thought` 建议改为 `thought_summary` 或 `rationale_summary`。
- Parser 必须处理：
  - 非法 JSON
  - 未知 `type`
  - 缺少字段
  - 未知工具
  - 工具参数 schema 不匹配

### 3.3 Tool 合同

每个工具固定包含：

```text
name
description
parameters_schema
run
timeout
is_async
permission
```

MVP 工具：

```text
calculator
weather
todo
```

后续工具：

```text
search
long_search
```

`todo` 工具建议 action：

```text
add
list
done
```

需要提前明确：

- `done` 使用 `todo_id` 还是 `content`。
- todo 的 `status` 枚举。
- todo 是否支持 `due_time`。

### 3.4 数据库合同

MVP SQLite 表：

```text
sessions
messages
todos
tool_traces
```

异步阶段增加：

```text
async_jobs
```

长期记忆阶段增加：

```text
user_profiles
user_profile_facts
semantic_memories
episodic_memories
```

关键规则：

- `messages`、`todos`、`tool_traces`、`async_jobs` 必须绑定 `user_id + session_id`。
- 长期记忆可按 `user_id` 跨 session 召回，但不能跨 user。
- DB 应作为事实源，`SessionState` 只是聚合视图，避免双写漂移。

### 3.5 状态机合同

Session 状态：

```text
idle
running
waiting_tool
waiting_async_tool
completed
error
```

说明：

- `waiting_tool` 对同步工具可能只是瞬时状态，测试中不一定强行断言。
- 端到端验收应关注最终状态与 trace。

Async job 状态：

```text
submitted
running
completed
failed
cancelled
```

### 3.6 错误码合同

建议最小错误码：

```text
LLM_API_ERROR
INVALID_LLM_OUTPUT
UNKNOWN_TOOL
INVALID_TOOL_ARGUMENTS
TOOL_TIMEOUT
TOOL_EXECUTION_ERROR
CONTEXT_TOO_LONG
SESSION_NOT_FOUND
DB_ERROR
MAX_STEPS_EXCEEDED
```

测试应优先按错误码断言，而不是按长错误文本断言。

### 3.7 Trace 合同

Trace 应记录：

```text
trace_id
user_id
session_id
step
action_type
thought_summary
tool_name
arguments
result_summary
latency_ms
status
error
created_at
```

Trace 不应记录：

```text
完整 chain-of-thought
真实 API key / token / secret
过长原始工具返回
```

---

## 4. 最终推荐 Issues 顺序

以下顺序为修正后的垂直切片顺序。每个 issue 都应包含代码、测试、可运行命令和可观察输出。

---

## Issue 1：项目骨架与核心合同冻结

**Type**：AFK  
**Blocked by**：None

### What to build

搭建最小 Python / FastAPI 项目骨架，并冻结核心协议与数据模型。

包括：

- 目录结构
- Pydantic DTO
- LLM 输出协议
- Tool schema 协议
- SessionState 模型
- 错误类型
- FakeLLM / ScriptedLLM 接口
- SQLite 初始化
- pytest 基础配置
- `.env.example`
- `requirements.txt`

### Acceptance criteria

- [ ] `app` 可以正常导入。
- [ ] `pytest` 可以运行。
- [ ] 存在 `requirements.txt`。
- [ ] 存在 `.env.example`，且不包含真实密钥。
- [ ] 明确 LLM 输出 JSON 协议。
- [ ] 明确 SessionState、Tool schema、错误码。
- [ ] 明确 SQLite 最小表结构。
- [ ] FastAPI app 可以启动。

---

## Issue 2：单 Session 最小 Agent Loop：final 直答

**Type**：AFK  
**Blocked by**：Issue 1

### What to build

实现最小单 session Agent Loop，只处理 FakeLLM 返回 `final` 的直接回复路径。

包括：

- Session Manager
- messages 持久化
- LLM Client 抽象
- FakeLLM
- Action Parser 解析 `final`
- Runtime 返回最终答案

### Acceptance criteria

- [ ] 用户输入会保存为 user message。
- [ ] FakeLLM 返回 `final`。
- [ ] Parser 能解析 `final`。
- [ ] Runtime 返回 `answer`。
- [ ] assistant message 写入指定 `user_id + session_id`。
- [ ] 单 session final 直答测试通过。

---

## Issue 3：Tool Registry + calculator 闭环

**Type**：AFK  
**Blocked by**：Issue 2

### What to build

实现 Tool 基类、Tool Registry、calculator 工具，并跑通：

```text
用户输入 -> FakeLLM tool_call -> calculator -> 工具结果回写 -> FakeLLM final -> 最终答案
```

### Acceptance criteria

- [ ] Tool Registry 支持注册工具。
- [ ] Tool Registry 支持查询工具。
- [ ] Tool Registry 支持输出工具 schema。
- [ ] 重复注册同名工具会报错。
- [ ] 未知工具会报错。
- [ ] calculator 支持基础数学表达式。
- [ ] 工具参数缺失会报错。
- [ ] 非法 JSON 会报错。
- [ ] `2 + 3 * 4` 最终返回 `14`。
- [ ] 相关 pytest 通过。

---

## Issue 4：Trace Logger + 异常 / max_steps 闭环

**Type**：AFK  
**Blocked by**：Issue 3

### What to build

实现 Trace Logger，并补齐工具异常、LLM 输出异常、max_steps fallback。

包括：

- LLM 决策 trace
- 工具调用 trace
- latency / status / error
- max_steps fallback
- 工具失败 fallback

### Acceptance criteria

- [ ] 成功工具调用链路写入 trace。
- [ ] 失败工具调用链路写入 trace。
- [ ] trace 包含 step、action_type、tool_name、arguments、result_summary。
- [ ] trace 包含 latency_ms、status、error。
- [ ] FakeLLM 无限返回 `tool_call` 时，Runtime 在 max_steps 后停止。
- [ ] max_steps 停止时写入 `MAX_STEPS_EXCEEDED` trace。
- [ ] Runtime 返回用户可理解 fallback。
- [ ] 相关 pytest 通过。

---

## Issue 5：Todo 工具 + 多 Session 隔离

**Type**：AFK  
**Blocked by**：Issue 4

### What to build

实现 todos 表和 todo 工具，并确保短期状态全部按 `user_id + session_id` 隔离。

包括：

- todo add
- todo list
- todo done
- messages 隔离
- todos 隔离
- trace 隔离

### Acceptance criteria

- [ ] `user_A + window_1` 可以添加 todo。
- [ ] `user_A + window_2` 可以添加 todo。
- [ ] 查询 `window_1` 只能看到 `window_1` 的 todo。
- [ ] 查询 `window_2` 只能看到 `window_2` 的 todo。
- [ ] messages 不跨 session 泄漏。
- [ ] trace 不跨 session 泄漏。
- [ ] 所有短期表查询均带 `user_id + session_id`。
- [ ] 相关 pytest 通过。

---

## Issue 6：Weather / Search mock + 多工具连续调用演示

**Type**：AFK  
**Blocked by**：Issue 5

### What to build

实现 weather/search mock 工具，并支持一次用户输入内连续调用多个工具。

目标 demo：

```text
北京今天天气怎么样？顺便帮我记一个待办：晚上 8 点带伞出门。
```

链路：

```text
weather -> todo -> final
```

### Acceptance criteria

- [ ] weather 工具返回 mock 天气。
- [ ] search 工具可返回 mock 搜索结果。
- [ ] Runtime 支持一次输入内连续调用多个工具。
- [ ] “查北京天气并记待办”可跑通。
- [ ] trace step 顺序正确。
- [ ] final answer 同时包含天气与待办记录结果。
- [ ] 相关 pytest 通过。

---

## Issue 7：Context Manager + 追问能力

**Type**：AFK  
**Blocked by**：Issue 6

### What to build

实现结构化 Context Manager，支持基于当前 session 的最近消息、工具结果、todo、summary 构建上下文。

Context 推荐顺序：

```text
System Prompt
Tool Schemas
User Profile
Relevant Long-term Memory
Session Summary
Active Tasks
Recent Tool Results
Recent Messages
Current User Input
```

MVP 阶段可先实现：

```text
System Prompt
Tool Schemas
Session Summary
Todos
Recent Tool Results
Recent Messages
Current User Input
```

### Acceptance criteria

- [ ] Context 不直接塞入全部历史消息。
- [ ] Context 包含 recent messages。
- [ ] Context 包含 recent tool results。
- [ ] Context 包含当前 session todos。
- [ ] Context 不包含其他 session 内容。
- [ ] `window_1` 查天气后追问“晚上要带伞吗”，能基于当前 session 的 weather 结果回答。
- [ ] `window_2` 不被 `window_1` 的天气结果污染。
- [ ] 相关 pytest 通过。

---

## Issue 8：Context 压缩 + session summary 更新

**Type**：AFK  
**Blocked by**：Issue 7

### What to build

实现 context 压缩策略，支持按轮次或估算 token 阈值压缩旧消息，更新 session summary。

压缩策略：

```text
最近原文 + 历史摘要 + 关键事实
```

### Acceptance criteria

- [ ] 支持按消息轮数触发压缩。
- [ ] 支持按估算 token / 字符数触发压缩。
- [ ] 最近 6 到 10 轮消息保留原文。
- [ ] 更早消息压缩进 session summary。
- [ ] todo 不丢失。
- [ ] active tasks 不丢失。
- [ ] recent tool results 的关键摘要不丢失。
- [ ] 压缩后追问仍可回答。
- [ ] 长对话模拟测试通过。

---

## Issue 9：长期记忆最小闭环

**Type**：AFK  
**Blocked by**：Issue 8

### What to build

实现长期记忆最小闭环，包括：

- Memory Manager 接口
- user profile
- semantic memory
- episodic memory
- mock vector store 或轻量关键词检索
- 按 `user_id` 过滤召回

### Acceptance criteria

- [ ] 支持 user profile 结构化读写。
- [ ] 支持 semantic memory 写入与召回。
- [ ] 支持 episodic memory 写入与召回。
- [ ] 用户提到“之前 / 上次 / 继续”时触发召回。
- [ ] 长期记忆只按同一 `user_id` 召回。
- [ ] 不同 user 之间不会泄漏长期记忆。
- [ ] 召回结果能进入 context。
- [ ] 相关 pytest 通过。

---

## Issue 10：异步工具 + 事件队列最小闭环

**Type**：AFK  
**Blocked by**：Issue 7 或 Issue 8

### What to build

实现异步工具和事件队列最小闭环。

包括：

- async_jobs 表
- long_search 异步工具
- Session Event Queue
- ToolCompletedEvent
- running / busy 状态处理
- 同 session 单 writer 原则

### Acceptance criteria

- [ ] long_search 提交后立即返回 `job_id`。
- [ ] async_jobs 保存 job 状态。
- [ ] 可以模拟异步任务完成。
- [ ] 完成后写入 ToolCompletedEvent。
- [ ] 当前 session 可以读取异步结果。
- [ ] 异步结果不会写入其他 session。
- [ ] CancelEvent 优先级至少有测试覆盖。
- [ ] 同 session 单 writer 至少有测试覆盖。
- [ ] 所有异步事件写入 trace。
- [ ] 相关 pytest 通过。

---

## Issue 11：CLI / FastAPI 演示入口 + trace 查询

**Type**：AFK  
**Blocked by**：Issue 6、Issue 7、Issue 8

如果要展示 memory / async，则额外依赖 Issue 9 / Issue 10。

### What to build

实现最小 CLI 或 FastAPI 路由，支持文档第 28 节录屏流程。

至少支持：

- 创建 session
- 发送消息
- 查询 todo
- 查询 trace

### Acceptance criteria

- [ ] FastAPI 可以创建 session。
- [ ] FastAPI 可以发送消息并返回 Agent 回复。
- [ ] FastAPI 可以查询当前 session todos。
- [ ] FastAPI 可以查询当前 session trace。
- [ ] CLI 可以指定 `user_id + session_id` 发送消息。
- [ ] `/trace window_1` 或等价命令能输出 step 序列。
- [ ] 文档第 28 节 window_1 / window_2 录屏流程可跑通。
- [ ] FastAPI 与 CLI 复用同一 runtime。
- [ ] 相关 pytest 或集成测试通过。

---

## Issue 12：README、Demo Docs、问题解决记录与全量回归

**Type**：AFK  
**Blocked by**：Issue 11

### What to build

补齐提交材料：

- README
- `docs/design.md`
- `docs/prompts.md`
- `docs/problem_solving_log.md`
- `docs/demo_script.md`
- 全量 pytest 回归

### Acceptance criteria

- [ ] README 包含项目简介。
- [ ] README 包含技术栈。
- [ ] README 包含快速启动。
- [ ] README 包含 Agent Runtime 设计。
- [ ] README 包含 Session / Memory / Context / Tool / Trace 说明。
- [ ] `docs/prompts.md` 记录关键 AI Prompt。
- [ ] `docs/problem_solving_log.md` 记录开发问题和解决方式。
- [ ] `docs/demo_script.md` 支持录屏演示。
- [ ] `pytest tests/` 全部通过。
- [ ] 手动演示覆盖 session 隔离、追问、trace、异常至少一种。
- [ ] 文档中的命令与实际项目一致。

---

## 5. 检查并修正的问题

### 5.1 不按原文第 31 节机械横向拆分

原文第 31 节顺序是：

```text
第一阶段 Runtime 主流程
第二阶段 Context 和 Memory
第三阶段 异步和测试
```

这个顺序适合设计说明，但不适合直接作为 issue 拆解。

问题：

- 测试太晚。
- Trace 太晚。
- Session 隔离没有端到端验收。
- Memory 可能早于稳定 Agent Loop。
- 每个阶段完成后不一定可演示。

修正：

- 改为 12 个可验收垂直切片。
- 每个 issue 都包含 pytest、可运行命令、可观察输出。

### 5.2 FakeLLM 必须前置

不能让核心测试依赖真实 LLM。

修正：

- Issue 1 冻结 FakeLLM 接口。
- Issue 2 开始用 FakeLLM 验证 final 直答。
- 后续 tool_call、max_steps、异常路径都用 ScriptedLLM 测试。

### 5.3 Trace 不能最后做

Trace 是 debug、测试、录屏证明的关键能力。

修正：

- Trace 放到 Issue 4。
- 后续 todo、weather、多工具、异步、异常都必须写 trace。

### 5.4 Session 隔离是最高风险

所有短期状态必须绑定：

```text
user_id + session_id
```

修正：

- Todo、多 session、messages、trace 隔离集中在 Issue 5 做端到端验收。
- 长期记忆只按 `user_id` 跨 session，但不能跨 user。

### 5.5 Tool Registry 与 Trace Logger 职责要分清

风险：

- Tool Registry 写 trace。
- Runtime 也写 trace。
- 造成双写或漏写。

修正建议：

```text
Tool Registry：注册、查询、schema 输出、参数校验、执行工具
Runtime：编排工具调用、写 trace、处理 fallback
Trace Logger：只负责落库/查询 trace
```

### 5.6 SessionState 与 DB 避免双写漂移

风险：

- SessionState 有 todos、tool_traces。
- DB 也有独立 todos、tool_traces 表。

修正建议：

```text
DB 是事实源
SessionState 是聚合视图
不要在内存状态和 DB 中维护两套互相独立的数据
```

### 5.7 `thought` 字段改为 `thought_summary`

原文 LLM 输出协议包含 `thought`，但又要求不保存完整 chain-of-thought。

修正：

```text
thought -> thought_summary
```

只记录简短决策摘要，不记录完整推理。

### 5.8 Context 压缩的 token_count 可降级

MVP 中可以不接真实 tokenizer。

修正：

- 可先用字符数或估算 token。
- 验收标准中必须说明是估算，不要假装已有 tokenizer。

### 5.9 不把定时任务 / Reminder 混入 MVP

Reminder 依赖：

- memory
- summary
- scheduler
- notification

修正：

- 暂不进入 MVP issue。
- 可作为后续扩展 issue。

---

## 6. MVP 优先级

### 6.1 必做 MVP

```text
Issue 1  项目骨架与核心合同冻结
Issue 2  单 session final 直答 Agent Loop
Issue 3  Tool Registry + calculator 闭环
Issue 4  Trace Logger + 异常 / max_steps 闭环
Issue 5  Todo 工具 + 多 Session 隔离
Issue 6  Weather/Search mock + 多工具连续调用
Issue 7  Context Manager + 追问能力
Issue 11 CLI / FastAPI 演示入口 + trace 查询
Issue 12 README、Demo Docs、问题解决记录与全量回归
```

### 6.2 加分项

```text
Issue 8  Context 压缩 + session summary 更新
Issue 9  长期记忆最小闭环
Issue 10 异步工具 + 事件队列最小闭环
```

### 6.3 暂缓项

```text
真实 Chroma / FAISS 深度集成
PostgreSQL
Redis / Celery
React / Vue 前端
OpenTelemetry
复杂 Multi-Agent
Scheduler / Reminder
复杂权限系统
```

---

## 7. 最终验收建议

最终提交前至少运行：

```text
pytest tests/
```

并手动跑通：

```text
启动项目
创建 window_1
创建 window_2
window_1 查询北京天气并添加带伞 todo
window_2 生成周报并添加 README todo
查询 window_1 todo，只看到带伞 todo
查询 window_2 todo，只看到 README todo
window_1 追问晚上是否需要带伞
查询 window_1 trace
展示异常 / max_steps fallback 至少一种
```

最终 README 和 demo script 必须与实际命令一致。
