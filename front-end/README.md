# Multi-Session Agent Frontend

这是 `Multi-Session Personal Productivity Agent` 的前端界面，用来连接项目根目录中的 FastAPI Agent 后端。

## 已接入的后端能力

前端调用当前后端已经实现的认证与 Agent API：

- `POST /auth/register`：注册用户并获取 bearer token
- `POST /auth/login`：登录并获取 bearer token
- `GET /auth/me`：用 token 恢复当前用户
- `POST /auth/logout`：退出并撤销 token
- `GET /sessions`：查询当前登录用户拥有的 session 列表
- `POST /sessions`：为当前登录用户创建新 session
- `GET /sessions/{session_id}/messages`：加载当前 session 的可见聊天消息
- `POST /sessions/{session_id}/messages`：发送用户消息并接收 Agent 回复
- `GET /sessions/{session_id}/todos`：查询当前 session 的待办
- `GET /sessions/{session_id}/trace`：查询当前 session 的 Agent 执行轨迹

前端不会再暴露手动 `user_id` / `session_id` 输入，也不会在受保护 API 中传 `user_id`。用户身份由后端 bearer token 决定。

## 本地运行

先在项目根目录启动后端，二选一：

```bash
# 确定性演示，不需要真实 API Key
python start_manual_demo.py
```

或：

```bash
# 真实 LLM 服务，需要根目录 .env 配置
python start_server.py
```

再启动前端：

```bash
cd front-end
npm install
npm run dev
```

打开页面后先注册或登录，然后从左侧创建新对话、切换自己的 session。

Vite 默认会把前端请求的 `/api/*` 代理到 `http://127.0.0.1:8000/*`，所以前端代码默认不需要直接写后端域名。

## 配置 API 地址

默认：

```env
VITE_API_BASE=/api
```

如果不使用 Vite 代理，也可以在前端环境变量中指定完整后端地址，例如：

```env
VITE_API_BASE=http://127.0.0.1:8000
```

## 验证

```bash
npm run typecheck
npm run build
```
