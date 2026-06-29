# AI Prompt 与问题解决记录

本文记录当前项目中与 AI Prompt、工具调用、memory 抽取、上下文组织和问题修复相关的关键设计。它面向后续维护者，用来快速理解：模型被要求输出什么、工具如何暴露给模型、工具结果如何进入上下文，以及近期真实调试过程中解决了哪些问题。

---

## 1. 项目中的 AI Prompt 分层

当前项目有两类主要 prompt：

1. Agent Runtime 决策 prompt
   - 文件：`app/llm/openai_client.py`
   - 目标：让模型在每轮 Agent loop 中只输出项目自定义 JSON action。

2. 长期记忆抽取 prompt
   - 文件：`app/memory/extractor.py`
   - 目标：从单轮对话中抽取用户画像、语义记忆和情节记忆。

这两类 prompt 的职责不同：Runtime prompt 决定“本轮要不要调用工具、如何回答”；Memory prompt 决定“本轮对话中有什么值得长期保存”。

---

## 2. Agent Runtime 决策 Prompt

### 2.1 Prompt 目标

Runtime prompt 要求模型扮演“Agent Runtime 决策器”，只输出 JSON 对象。它不要求模型直接执行工具，也不使用 OpenAI 原生 `tools` / `tool_calls`。

模型只能输出两种 action：

```json
{
  "type": "final",
  "thought_summary": "...",
  "answer": "..."
}
```

或：

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

### 2.2 当前 Runtime Prompt 要点

当前 `OpenAICompatibleClient.complete(...)` 的系统提示词核心约束是：

```text
你是一个 Agent Runtime 决策器。必须只输出 JSON 对象，
格式为 {type: 'final', thought_summary: string, answer: string}
或 {type: 'tool_call', thought_summary: string, tool_name: string, arguments: object}。
你会在上下文中收到 available_tools，里面列出当前已注册工具的 name、description 和 parameters。
你还会收到 current_turn_events，它按顺序记录当前用户请求、本轮 assistant_action tool_call 和 tool_result。
current_user_input 和 current_turn_events 中的最新 user 内容是当前必须处理的请求；recent_messages、relevant_long_term_memory、session_summary 只能作为背景，不能覆盖当前请求。
生成 tool_call 时，工具参数必须来自当前用户请求或当前轮 tool_result，不能从历史消息或长期记忆中拿旧关键词替代当前请求。
如果用户请求能由 available_tools 中任一工具完成，并且 current_turn_events 中还没有可用 tool_result，必须先输出 tool_call，并按该工具 parameters 提供 arguments。
工具结果会作为 tool_result 加入下一轮 current_turn_events。
当 current_turn_events 最后一项或 recent_tool_results 已经包含能回答当前请求的工具结果时，必须输出 final，不要重复调用同一个工具。
当 available_tools 中已有可用工具能处理请求时，不能直接回答无法获取或建议用户自行查询。
```

### 2.3 为什么不用 OpenAI 原生 tool call

当前项目刻意使用项目自有 JSON action 协议，而不是 OpenAI 原生 tool call。原因是：

- Runtime 更可控：所有模型输出统一交给 `ActionParser` 校验。
- 测试更稳定：`ScriptedLLM` 可以直接返回 action dict，不依赖真实模型。
- 可替换模型：只要模型能返回 JSON，就能接入 OpenAI-compatible API。
- 教学更清晰：工具注册、上下文构建、工具执行、trace 都在项目代码里显式可见。

因此真实 HTTP 请求仍然是普通 chat completion：

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "Runtime decision prompt"},
    {"role": "user", "content": "serialized context JSON"}
  ],
  "temperature": 0
}
```

模型返回的 `message.content` 必须是 JSON 字符串，由项目自己解析。

---

## 3. 工具注册与 Prompt 的关系

### 3.1 工具不是硬编码进 prompt

工具类通过 `ToolRegistry` 注册：

```python
registry.register(CalculatorTool())
registry.register(WeatherTool())
registry.register(SearchTool())
registry.register(TodoTool(session_manager))
registry.register(LongSearchTool(async_manager))
```

每个工具暴露：

- `name`
- `description`
- `parameters_schema`
- `run(...)`
- `timeout`
- `is_async`
- `permission`

`ToolRegistry.schemas()` 会动态生成给模型看的工具信息：

```json
{
  "name": "weather",
  "description": "查询指定城市的天气。",
  "parameters": {
    "type": "object",
    "properties": {
      "city": {
        "type": "string",
        "description": "城市名，例如 北京、上海、首尔"
      }
    },
    "required": ["city"]
  }
}
```

Runtime 每轮构建 context 时追加：

```json
{
  "section": "available_tools",
  "items": [
    "...当前所有已注册工具 schema..."
  ]
}
```

因此扩展新工具时，只要注册到 `ToolRegistry`，模型就能在 `available_tools` 中看到它，不需要修改系统 prompt 去硬编码工具名。

### 3.2 工具调用执行流程

完整流程：

```text
用户输入
  -> AgentRuntime.handle_user_message(...)
  -> ContextManager.build_context(...)
  -> 追加 current_turn_events
  -> 追加 available_tools
  -> llm_client.complete(context)
  -> ActionParser.parse(...)
  -> ToolRegistry.execute(tool_name, arguments, context={user_id, session_id})
  -> tool_result 写入 SQLite message 和 trace
  -> tool_result 追加到 current_turn_events
  -> 再次调用模型
  -> final
```

关键点：工具执行依赖后端注入的 `user_id + session_id`，不是前端传入的可伪造身份。

---

## 4. 当前轮上下文策略

### 4.1 为什么需要 current_turn_events

早期实现只有 `recent_tool_results`，模型可能不知道工具结果属于当前用户问题，或在看到结果后继续重复调用工具。

现在 Runtime 在当前轮中维护事件序列：

```text
user question
assistant_action tool_call
tool_result
assistant final
```

对应 context：

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

这样模型能明确看到：当前问题已经调用过工具，而且工具结果就在本轮问题之后。

### 4.2 重复工具调用保护

除了 prompt 约束，Runtime 还做代码级保护：

- 按 `tool_name + arguments` 序列化生成 key。
- 当前轮执行过的工具调用放入 `executed_tools`。
- 如果模型重复请求相同工具调用，Runtime 不再重复执行工具，而是复用已有工具结果并 finalize。

这解决了真实模型反复调用 `weather` 直到 `MAX_STEPS_EXCEEDED` 的问题。

---

## 5. Memory 抽取 Prompt

### 5.1 Prompt 目标

长期记忆抽取 prompt 位于 `LLMMemoryExtractor._SYSTEM_PROMPT`。它只负责从单轮对话中抽取长期有效、非敏感的信息。

输出必须是 JSON 对象：

```json
{
  "profile_updates": {
    "preferred_language": "中文",
    "answer_style": "简洁直接",
    "common_topics": ["Agent Runtime"],
    "timezone": "Asia/Shanghai"
  },
  "semantic_memories": [
    "用户偏好用中文回答。"
  ],
  "episodic_memories": [
    {
      "event_type": "turn_completed",
      "content": "用户询问北京天气并获得天气工具结果。",
      "summary": "北京天气查询完成",
      "importance": 0.5
    }
  ]
}
```

### 5.2 Memory Prompt 规则

核心规则：

- 只保存用户明确表达或对话强支持的长期事实。
- 不保存 API key、token、password、secret、私钥、密钥、凭据或私有连接信息。
- `profile_updates` 只能使用：
  - `preferred_language`
  - `answer_style`
  - `common_topics`
  - `timezone`
- `semantic_memories` 保存稳定事实或偏好。
- `episodic_memories` 保存本轮值得跨 session 召回的事件。
- `importance` 取 `0` 到 `1`。
- 没有可保存内容时返回空对象 / 空数组。

### 5.3 Memory 抽取失败时怎么办

`LLMMemoryExtractor` 调用失败、超时或输出结构不合法时，会回退到 `HeuristicMemoryExtractor`。

这保证 memory 写入是 best-effort，不影响主对话响应。

---

## 6. Memory 召回与放置方式

### 6.1 写入时机

一次对话成功 `final` 后，Runtime 调用：

```text
AgentRuntime._finalize(...)
  -> AgentRuntime._update_memory_after_turn(...)
    -> MemoryManager.update_from_turn(...)
```

也就是说，长期记忆写入发生在最终回答之后。工具失败、模型协议错误或 fallback 不会阻塞用户响应。

### 6.2 召回时机

每次构建 LLM context 时都会尝试召回：

```text
AgentRuntime._build_llm_context(...)
  -> ContextManager.build_context(...)
    -> MemoryManager.retrieve(user_id, current_input)
```

召回优先级：

1. Chroma 向量召回。
2. 如果 Chroma 不可用、失败或无结果，则退回 SQLite 触发词召回。

SQLite fallback 触发词包括：

```text
之前、上次、继续、还记得、过去
```

### 6.3 Memory 放入上下文的位置

`ContextManager.build_context(...)` 生成结构化 context：

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
- `relevant_long_term_memory` 放召回到的 semantic / episodic memory。
- `session_summary` 放当前 session 压缩摘要。
- `recent_messages` 放当前 session 最近消息。
- `current_user_input` 放本轮用户问题。

随后 Runtime 再追加：

```text
current_turn_events
available_tools
```

最终发给模型的是结构化 JSON context，而不是把所有内容拼成一个不可区分的长 prompt。

---

## 7. 问题解决记录

### 问题 1：问“今天北京的天气”没有调用 weather 工具

**现象**

模型直接回答“无法获取实时天气”，没有触发项目中的 weather 工具。

**原因**

工具虽然已经在后端注册，但没有把已注册工具的 `name`、`description`、`parameters_schema` 暴露给 LLM。模型不知道可以调用哪些工具。

**解决**

Runtime 构建 context 时追加：

```json
{
  "section": "available_tools",
  "items": "ToolRegistry.schemas()"
}
```

Prompt 明确要求：当 `available_tools` 中有工具能处理用户请求时，必须先输出 `tool_call`，不能直接说无法获取。

---

### 问题 2：工具注册不能硬编码

**需求**

用户要求扩展工具时能够注册进系统，而不是在 prompt 中手写 `weather`、`search` 等固定工具。

**解决**

保留 ToolRegistry 为唯一工具注册入口：

```python
registry.register(MyTool())
```

每轮通过 `ToolRegistry.schemas()` 动态生成 `available_tools`。因此新增工具只需要实现工具类并注册，不需要改 Runtime prompt 的工具列表。

---

### 问题 3：误以为模型会返回 OpenAI 原生 tool_call

**澄清**

当前项目没有使用 OpenAI 原生 tool call。模型返回的是普通 message content，只不过内容必须是项目规定的 JSON action。

**当前事实**

- HTTP API：OpenAI-compatible `/chat/completions`。
- `messages[0]`：Runtime system prompt。
- `messages[1]`：序列化后的 context JSON。
- 模型返回：JSON 字符串。
- 项目解析：`ActionParser`。
- 工具执行：`ToolRegistry.execute(...)`。

---

### 问题 4：weather 工具重复调用直到 MAX_STEPS_EXCEEDED

**现象**

一次天气问题产生多次相同 `weather` tool_call / tool_result，最后触发 `MAX_STEPS_EXCEEDED`。

**原因**

只有 `recent_tool_results` 不足以让模型稳定理解“当前问题已经有工具结果”。同时 Runtime 缺少重复工具调用去重。

**解决**

1. 增加 `current_turn_events`，按顺序记录：

```text
user -> assistant_action tool_call -> tool_result
```

2. Prompt 要求：如果当前轮已有可回答的 `tool_result`，必须输出 `final`。

3. Runtime 增加重复工具调用保护：

```text
tool_key = json.dumps({tool_name, arguments}, sort_keys=True)
```

同一轮重复调用相同工具时，直接复用已有结果并 finalize。

---

### 问题 5：工具结果应该放到当前用户问题之后

**需求**

工具调用 action 和 tool result 应该出现在当前 turn 内，而不是只放在一个“最近工具结果”区域。

**解决**

新增 `current_turn_events`，显式表达当前轮序列：

```text
用户问题
助手工具请求
工具结果
助手最终回答
```

这比单独的 `recent_tool_results` 更接近 OpenAI-style message sequence，也能减少模型误用历史工具结果。

---

### 问题 6：前端 trace 显示混乱

**现象**

同一个 session 里先问天气、再搜索资料后，前端 trace 看起来交叉混在一起。

**原因**

前端按 `step` 排序 trace，但 `step` 是每个用户 turn 内部的步骤，跨 turn 会重复从 1 开始。

**解决**

前端不再执行：

```ts
sort((a, b) => a.step - b.step)
```

改为保留后端返回顺序。后端按数据库插入顺序返回 trace，能反映真实执行时间线。

---

### 问题 7：E2E 中前端请求后端出现 CORS 问题

**现象**

隔离 E2E 后端使用非默认端口时，前端用绝对 `VITE_API_BASE` 直接跨域请求后端，浏览器触发 CORS 问题。

**解决**

Vite proxy 支持可配置目标：

```ts
const apiProxyTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
```

前端仍请求同源 `/api`，由 Vite 转发：

```ts
server: {
  proxy: {
    '/api': {
      target: apiProxyTarget,
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
}
```

---

### 问题 8：搜索工具参数漂移到历史问题

**现象**

第二个 session 中搜索新资料时，真实模型仍把旧问题“今天北京的天气”作为 `search.query`。

**原因**

Prompt 没有明确要求当前用户输入优先于历史消息、长期记忆和 session summary。

**解决**

Prompt 增加约束：

- `current_user_input` 和 `current_turn_events` 中最新 user 内容是当前必须处理的请求。
- `recent_messages`、`relevant_long_term_memory`、`session_summary` 只能作为背景。
- 工具参数必须来自当前用户请求或当前轮 tool result，不能从历史里拿旧关键词替代当前请求。

---

### 问题 9：刷新页面后进入新 session

**现象**

第一个 session 提问后刷新页面，前端回到空白 / 新 session 状态。

**原因**

前端没有持久化 active session id。

**解决**

前端 localStorage 保存：

```text
msa_active_session_id
```

刷新后先恢复登录态，再拉 `/sessions`，优先打开保存的 active session。

---

### 问题 10：一个 session 正在等待时，另一个 session 不能发送消息

**现象**

第一个 session 的回答还没回来时，切到第二个 session，输入框仍被全局 sending 状态禁用。

**原因**

前端原来只有全局 `sending` 状态。

**解决**

改为 per-session sending state：

```ts
const [sendingSessionIds, setSendingSessionIds] = useState<Set<string>>(() => new Set())
```

当前 session 是否禁用由：

```ts
const currentSessionSending = sendingSessionIds.has(activeSessionId ?? PENDING_NEW_SESSION_ID)
```

决定。不同 session 之间互不阻塞。

---

### 问题 11：刷新时 Agent 运行中的 loading 消失

**现象**

当前 active session 仍在后端运行，但页面刷新后 `Agent 正在运行…` loading 气泡消失。

**原因**

loading 气泡原本只存在于前端内存状态中，刷新后没有从后端 session status 重建。

**解决**

前端加载 session 时检查状态：

```ts
status === 'running' || status === 'waiting_tool' || status === 'waiting_async_tool'
```

如果仍在运行，则恢复 loading 气泡，并把当前 session 加入 `sendingSessionIds`。

同时新增 polling：当前 active session 仍 sending 时，定时拉 `/sessions` 并重新加载 messages / todos / trace；完成后清除 sending 状态，loading 替换为最终回答。

---

## 8. 后续维护建议

1. 新增工具时：
   - 实现工具类；
   - 提供准确的 `name`、`description`、`parameters_schema`；
   - 注册到 `ToolRegistry`；
   - 写测试确认 `available_tools` 能看到它。

2. 修改 Runtime prompt 时：
   - 保持“只输出 JSON action”；
   - 保持当前输入优先级高于历史和 memory；
   - 保持工具结果存在时应 final；
   - 用真实模型 E2E 验证不会重复 tool_call。

3. 修改 memory 逻辑时：
   - 不保存密钥、token、密码、私有 URL；
   - 保持 `user_id` 过滤；
   - 保持 SQLite 为事实源，Chroma 为索引；
   - 记忆抽取失败不能影响主响应。

4. 修改前端 session 状态时：
   - 注意 active session 持久化；
   - 注意 per-session sending；
   - 注意后台 session 完成后不要污染当前 active session UI；
   - 注意 trace 顺序应保留后端时间线。
