# Multi-Session Personal Productivity Agent

一个从零实现的多 Session 个人效率 Agent Demo。项目包含 FastAPI 后端、SQLite / Chroma 记忆层、手搓 Agent Runtime、动态工具注册、执行 trace，以及 Vite React 前端。

项目重点不是“调用某个 Agent 框架”，而是把 Agent 的关键链路拆开：上下文如何构建、工具如何注册给模型、工具结果如何回到上下文、长期记忆何时写入与召回、前端如何恢复 session 状态。

---

## 1. 功能概览

- 用户注册、登录、登出。
- Bearer token 认证，后端从 token 推导 `user_id`。
- 用户只能看到和操作自己的 session。
- ChatGPT-like 前端：左侧 session 列表，右侧聊天主界面。
- 多 session 对话隔离。
- 支持工具调用：`calculator`、`weather`、`search`、`todo`、`long_search`。
- 支持工具 trace：记录 `tool_call`、`tool_result`、`final`、`fallback` 等执行步骤。
- 支持长期记忆：用户画像、语义记忆、情节记忆。
- 支持 SQLite + Chroma 向量召回。
- 支持刷新后恢复 active session；如果 Agent 仍在运行，会恢复 `Agent 正在运行…` loading 并轮询到完成。

---

## 2. 技术栈

### 后端

- Python
- FastAPI
- Pydantic
- SQLite 标准库
- httpx
- ChromaDB
- pytest

### 前端

- React 18
- TypeScript
- Vite
- Tailwind CSS
- lucide-react

---

## 3. 目录结构

```text
app/
├── main.py                # FastAPI API、认证依赖、runtime 装配
├── config.py              # .env 配置读取
├── contracts.py           # Pydantic DTO、枚举、错误码、状态合同
├── llm/                   # OpenAI-compatible client、ScriptedLLM
├── memory/                # 长期记忆抽取、存储、向量索引
├── runtime/               # AgentRuntime、SessionManager、ContextManager、TraceLogger、AsyncManager
├── storage/               # SQLiteStore 与表结构初始化
└── tools/                 # ToolRegistry 与具体工具

front-end/
├── src/app/App.tsx        # ChatGPT-like 前端主界面
├── vite.config.ts         # Vite dev proxy
└── package.json

docs/
└── ai_prompt_and_problem_solving.md

tests/                     # 后端、runtime、memory、frontend config 回归测试
```

---

## 4. 环境准备

建议使用项目已验证过的 Python 环境，例如 `pyside6-env`。也可以使用普通虚拟环境。

### 安装 Python 依赖

```bash
pip install -r requirements.txt
```

或在 conda 环境中：

```bash
conda activate pyside6-env
pip install -r requirements.txt
```

### 安装前端依赖

```bash
npm --prefix front-end install
```

---

## 5. 后端运行方式

### 5.1 一键启动前后端

服务器或本地已有依赖后，可以直接启动前后端：

```bash
chmod +x start_all.sh
./start_all.sh
```

脚本会优先使用 `.venv/bin/python`，没有 `.venv` 时自动使用系统 `python3`；同时启动后端 `start_server.py` 和前端 Vite dev server。

### 5.2 真实 LLM 后端

后端服务会读取本地 `.env`，并通过 OpenAI-compatible `/chat/completions` 接口调用模型。

创建 `.env`：

```env
OPENAI_API_BASE=<OpenAI-compatible API base>
OPENAI_API_KEY=<your-api-key>
OPENAI_MODEL=<model-name>
SQLITE_DB_PATH=./agent_runtime.db
VECTOR_STORE_PATH=./vector_store
MAX_AGENT_STEPS=5
MEMORY_EXTRACTOR_MODE=llm
MEMORY_EXTRACTOR_TIMEOUT_SECONDS=10
MEMORY_EXTRACTOR_MODEL=
MEMORY_EXTRACTOR_MAX_INPUT_CHARS=6000
```

注意：不要把真实 API Key 提交到仓库，也不要写入文档、日志或 memory。

启动服务：

```bash
python start_server.py
```

也可以直接用 uvicorn 启动 FastAPI app：

```bash
uvicorn app.main:app --reload
```

默认监听：

```text
http://127.0.0.1:8000
```

---

## 6. 前端运行方式

前端默认通过 Vite proxy 把 `/api/*` 转发到 `http://127.0.0.1:8000/*`。

```bash
npm --prefix front-end run dev -- --host 127.0.0.1
```

如果已经在 `front-end/` 目录内，也可以运行：

```bash
npm run dev
```

然后打开 Vite 输出的地址，例如：

```text
http://127.0.0.1:5173/
```

### 切换后端代理目标

如果后端不是 `8000` 端口，可以用 `VITE_PROXY_TARGET`：

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8010 npm --prefix front-end run dev -- --host 127.0.0.1 --port 5181
```

前端代码仍然请求同源 `/api`，由 Vite 代理到目标后端，避免浏览器跨域问题。

---

## 7. 使用流程

1. 启动后端。
2. 启动前端。
3. 打开前端页面。
4. 注册或登录。
5. 点击「新对话」或直接发送消息。
6. 左侧选择不同 session。
7. 点击「Session details」查看 todos 和 trace。

示例问题：

```text
今天北京的天气
```

如果真实模型按协议输出 `tool_call`，Runtime 会调用 `weather` 工具，并把工具结果放回当前轮上下文，再让模型输出最终回答。

---

## 8. 系统设计

### 8.1 API 与认证边界

认证接口：

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`

Session 与 Agent 接口：

- `GET /sessions`
- `POST /sessions`
- `GET /sessions/{session_id}/messages`
- `POST /sessions/{session_id}/messages`
- `GET /sessions/{session_id}/todos`
- `GET /sessions/{session_id}/trace`

受保护接口都需要：

```http
Authorization: Bearer <token>
```

后端只信任 token 解析出的当前用户，不信任前端传入 `user_id`。因此 session、message、todo、trace 都以当前用户为边界隔离。

### 8.2 Runtime 主循环

`AgentRuntime.handle_user_message(...)` 是核心入口。

流程：

1. `ensure_session`：确认当前 `user_id + session_id` 存在。
2. 设置 session 状态为 `running`。
3. 保存用户消息到 SQLite。
4. `ContextManager.compress_if_needed(...)`：只要消息数超过最近消息窗口，就把窗口外旧消息压缩到 session summary；真实 LLM runtime 默认使用 LLM 压缩，失败时回退规则摘要。
5. 构建 LLM context。
6. 调用 `llm_client.complete(context)`。
7. `ActionParser` 解析项目自有 JSON action。
8. 如果是 `final`：保存 assistant 消息、写 trace、更新长期记忆、设置 completed。
9. 如果是 `tool_call`：执行工具、写 tool result、把结果追加到当前轮事件，继续下一轮。
10. 如果模型输出非法、工具失败或超步数：写 fallback trace，设置 error。

### 8.3 LLM Action Contract

本项目没有使用 OpenAI 原生 `tools` / `tool_calls`。模型必须输出项目自定义 JSON action。

最终回答：

```json
{
  "type": "final",
  "thought_summary": "...",
  "answer": "..."
}
```

工具调用：

```json
{
  "type": "tool_call",
  "thought_summary": "...",
  "tool_name": "weather",
  "arguments": {
    "city": "北京"
  }
}
```

Runtime 解析 JSON 后由 `ToolRegistry` 执行工具。

### 8.4 动态工具注册

工具通过 `ToolRegistry` 注册：

```python
registry.register(CalculatorTool())
registry.register(WeatherTool())
registry.register(SearchTool())
registry.register(TodoTool(session_manager))
registry.register(LongSearchTool(async_manager))
```

每个工具提供：

- `name`
- `description`
- `parameters_schema`
- `run(...)`
- `timeout`
- `is_async`
- `permission`

Runtime 每轮构建 LLM context 时会把当前注册工具 schema 注入：

```json
{
  "section": "available_tools",
  "items": [
    {
      "name": "weather",
      "description": "查询指定城市的天气。",
      "parameters": {
        "type": "object",
        "properties": {
          "city": {"type": "string"}
        },
        "required": ["city"]
      }
    }
  ]
}
```

因此新增工具时，只要注册到 `ToolRegistry`，LLM 就能在 `available_tools` 中看到它，不需要在 prompt 中硬编码工具名。

### 8.5 当前轮工具上下文

为了避免模型反复调用同一个工具，Runtime 会维护当前轮事件：

```text
user question
assistant_action tool_call
tool_result
assistant final
```

对应 context section：

```json
{
  "section": "current_turn_events",
  "items": [
    {"role": "user", "content": "今天北京的天气"},
    {"role": "assistant_action", "type": "tool_call", "tool_name": "weather", "arguments": {"city": "北京"}},
    {"role": "tool_result", "tool_name": "weather", "content": "北京今天多云，下午可能有阵雨。"}
  ]
}
```

同时 Runtime 会记录本轮已经执行过的 `tool_name + arguments`。如果模型重复请求完全相同的工具调用，Runtime 会复用已有结果并 finalize，避免循环到 `MAX_STEPS_EXCEEDED`。

### 8.6 Trace

Trace 用来观察 Agent 每一步执行：

- `tool_call`
- `tool_result`
- `final`
- `fallback`
- `async_tool_submitted`
- `async_tool_completed`

前端保留后端返回顺序，不再按 `step` 重新排序，因为 `step` 在每个用户 turn 内会从 1 开始，跨 turn 排序会导致 trace 显示混乱。

### 8.7 前端状态恢复

前端使用 localStorage 保存：

- `msa_auth_token`
- `msa_active_session_id`

页面刷新后：

1. 先用 token 调 `/auth/me` 恢复登录态。
2. 调 `/sessions` 获取当前用户 session 列表。
3. 优先恢复 `msa_active_session_id` 对应 session。
4. 如果 session 状态是 `running` / `waiting_tool` / `waiting_async_tool`：
   - 恢复 `Agent 正在运行…` loading 气泡；
   - 恢复当前 session 的 sending 状态；
   - 启动轮询，直到后端状态完成或出错。

---

## 9. Memory 设计：召回时机与放置方式

本节说明的是 Agent 产品内的长期记忆，不是 Claude Code 项目记忆。

### 9.1 Memory 类型

长期记忆分三类：

1. `user_profile`
   - 用户画像。
   - 存储稳定偏好，例如语言、回答风格、常见主题、时区。
   - SQLite 是事实源。

2. `semantic_memories`
   - 语义记忆。
   - 存储长期稳定事实。
   - SQLite 保存权威内容，Chroma 保存向量索引。

3. `episodic_memories`
   - 情节记忆。
   - 存储每轮成功对话后的事件摘要。
   - SQLite 保存权威内容，Chroma 支持跨 session 语义召回。

### 9.2 写入时机

Memory 写入发生在一次用户消息成功得到 `final` 后。

调用链：

```text
AgentRuntime._finalize(...)
  -> AgentRuntime._update_memory_after_turn(...)
    -> MemoryManager.update_from_turn(...)
```

只有 final 成功后才 best-effort 更新长期记忆。工具失败、模型协议错误或 fallback 不会阻塞主响应。

### 9.3 写入方式

`MemoryManager.update_from_turn(...)` 输入：

- `user_id`
- `session_id`
- `user_input`
- `assistant_answer`
- `tool_summaries`

抽取器：

- 真实 LLM runtime 默认使用 `LLMMemoryExtractor`。
- 测试 / scripted runtime 或 `MEMORY_EXTRACTOR_MODE=heuristic` 使用 `HeuristicMemoryExtractor`。
- LLM 抽取失败时回退 heuristic。

写入流程：

1. 抽取 profile updates、semantic memories、episodic memories。
2. 清洗数据：
   - 只允许已知 profile key；
   - 过滤空内容；
   - 过滤 secret / token / password / API key 等敏感内容；
   - 限制长度；
   - clamp `importance` 到 `[0, 1]`。
3. profile 写入 `user_profiles`。
4. semantic 写入 `semantic_memories`。
5. episodic 写入 `episodic_memories`。
6. semantic / episodic 写入 SQLite 后，best-effort upsert 到 Chroma。
7. Chroma 成功后，把向量文档 id 回写到 SQLite 的 `embedding_id`。

### 9.4 召回时机

每次构建 LLM context 时都会尝试召回长期记忆。

调用链：

```text
AgentRuntime._build_llm_context(...)
  -> ContextManager.build_context(...)
    -> MemoryManager.retrieve(user_id, current_input)
```

召回逻辑：

1. 如果 Chroma 可用：
   - 按当前 `user_id` 过滤向量查询；
   - 查询 top-k；
   - 根据 Chroma hit 中的 SQLite id 回查 SQLite；
   - 再次校验 `user_id`；
   - 返回 semantic / episodic memory 内容。
2. 如果 Chroma 不可用、失败或对应类型结果不足：
   - 退回 SQLite 触发词召回；
   - semantic 触发词包括：`记住`、`偏好`、`项目`、`背景`、`重点`、`交付`、`技术栈` 等；
   - episodic 触发词包括：`之前`、`上次`、`过去`、`问过`、`说过`、`聊过`、`做过` 等；
   - `刚才` 被视为当前 session 短期语境，不触发跨 session episodic 召回；
   - 从当前用户的 semantic / episodic 表中按关键词和最近记录排序取有限条数。

### 9.5 Session 上下文压缩

当前短期上下文窗口默认保留最近 10 条消息。为了避免“已有 15 条消息但压缩阈值 30，前 5 条既不在 recent messages 也不在 summary”的空窗，Runtime 在每次用户消息写入后都会检查：

```text
len(messages) > recent_message_limit
```

只要超过最近窗口，就把窗口外旧消息压缩进 `session_summary`，同时继续保留最近 10 条原文消息。

真实 LLM runtime 默认使用 `LLMContextSummarizer`：

```text
ContextManager.compress_if_needed(...)
  -> LLMContextSummarizer.summarize(existing_summary, old_messages)
  -> OpenAICompatibleClient.complete_json(...)
  -> SessionManager.update_summary(...)
```

压缩 prompt 要求只输出：

```json
{"summary":"..."}
```

摘要会保留用户目标、偏好、项目背景、待办线索、工具结果、关键事实、未完成事项和重要约束；同时要求不要保存 API key、token、password、secret、私钥等敏感内容。LLM 压缩失败时，会回退到 `RuleBasedContextSummarizer`，用规则方式把旧消息追加进 summary，保证旧上下文不会静默丢失。

测试 / scripted runtime 默认使用规则摘要，避免单元测试依赖真实 LLM。

### 9.6 Memory 放入上下文的位置

`ContextManager.build_context(...)` 会生成以下 section：

```text
system_prompt
user_profile
relevant_long_term_memory
session_summary
todos
recent_tool_results
recent_messages
current_user_input
```

其中：

- `user_profile` 放用户画像。
- `relevant_long_term_memory` 放本轮召回的 semantic / episodic memory。
- `session_summary` 放当前 session 压缩摘要。
- `recent_messages` 放当前 session 最近消息。
- `current_user_input` 放当前用户输入。

随后 `AgentRuntime._build_llm_context(...)` 追加：

```text
current_turn_events
available_tools
```

最终 `OpenAICompatibleClient.complete_json(...)` 会把：

- system prompt 放到 OpenAI-compatible `messages[0].content`；
- 整个 context JSON 序列化后放到 `messages[1].content`。

也就是说，memory 不是拼进一个长字符串 prompt，而是作为结构化 context section 发送给模型。

---

## 10. 验证命令

### 后端 / Runtime 全量测试

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
```

或使用项目推荐 conda 环境：

```bash
PYTHONIOENCODING=utf-8 conda run --no-capture-output -n pyside6-env python -m pytest tests/ -q
```

### 前端类型检查

```bash
npm --prefix D:/PythonProject/bishi/front-end run typecheck
```

### 前端生产构建

```bash
npm --prefix D:/PythonProject/bishi/front-end run build
```

---

## 11. 常见问题

### 天气、搜索等工具为什么没有调用？

模型只有在 context 中看到 `available_tools` 并输出合法 `tool_call` JSON 时，Runtime 才会执行工具。当前实现已经把 `ToolRegistry.schemas()` 注入 `available_tools`。

### 这是 OpenAI 原生 tool call 吗？

不是。当前项目使用自定义 JSON action 协议。OpenAI-compatible API 只负责返回文本内容，内容必须是 JSON 对象。

### 工具执行结果怎么回到模型？

工具结果会加入当前轮 `current_turn_events`，下一轮模型会看到：

```text
user -> assistant_action tool_call -> tool_result
```

然后模型应该输出 `final`。

### 为什么要有重复工具调用保护？

真实模型有时会看到工具结果后继续重复请求同一个工具。Runtime 会用 `tool_name + arguments` 去重；如果重复，就复用已有结果并结束本轮，避免无限循环。

### 页面刷新后运行中状态如何恢复？

前端保存 active session id。刷新后重新拉 `/sessions` 和当前 session messages，如果发现状态仍在运行，会补一个 loading 气泡并轮询到完成。
