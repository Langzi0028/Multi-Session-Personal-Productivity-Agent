import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";

interface UserPublic {
  user_id: string;
  username: string;
}

interface AuthResponse {
  token: string;
  token_type: "bearer";
  user: UserPublic;
}

interface SessionSummary {
  user_id: string;
  session_id: string;
  status: string;
  summary: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
  message_count: number;
}

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  sessionStatus?: string;
  createdAt: Date;
  isLoading?: boolean;
}

interface MessageRecord {
  id: number;
  role: "user" | "assistant";
  content: string;
  token_count: number;
  created_at: string;
}

interface Todo {
  id: number | null;
  content: string;
  status: "pending" | "done";
  due_time: string | null;
  created_at: string;
  updated_at: string;
}

interface Trace {
  trace_id: string;
  user_id: string;
  session_id: string;
  step: number;
  action_type: string;
  thought_summary: string;
  tool_name: string | null;
  arguments: Record<string, unknown>;
  result_summary: string | null;
  latency_ms: number;
  status: string;
  error: string | null;
  created_at: string;
}

const rawApiBase = import.meta.env.VITE_API_BASE?.trim() || "/api";
const API_BASE = rawApiBase.replace(/\/+$/, "");
const APP_FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif';
const TOKEN_KEY = "msa_auth_token";
const ACTIVE_SESSION_KEY = "msa_active_session_id";
const PENDING_NEW_SESSION_ID = "__new_session__";
const MESSAGE_CACHE_LIMIT = 80;

type AuthMode = "login" | "register";

function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parseError(response: Response) {
  try {
    const data = await response.json();
    return typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

function toChatMessage(record: MessageRecord): ChatMessage {
  return {
    id: String(record.id),
    role: record.role === "assistant" ? "agent" : "user",
    content: record.content,
    createdAt: new Date(record.created_at),
  };
}

function newId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function titleForSession(session: SessionSummary) {
  if (session.summary.trim()) return session.summary.trim();
  if (session.last_message_preview.trim()) return session.last_message_preview.trim();
  return "新对话";
}

function relativeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

function isSessionRunning(status: string) {
  return status === "running" || status === "waiting_tool" || status === "waiting_async_tool";
}

function restoreRunningSessionLoading(messages: ChatMessage[], session: SessionSummary): ChatMessage[] {
  if (!isSessionRunning(session.status)) return messages;
  if (messages.some((message) => message.isLoading)) return messages;
  return [
    ...messages,
    {
      id: `restored_loading_${session.session_id}`,
      role: "agent" as const,
      content: "",
      createdAt: new Date(),
      isLoading: true,
    },
  ].slice(-MESSAGE_CACHE_LIMIT);
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, [string, string, string]> = {
    idle: ["空闲", "#6E6E73", "#6E6E7314"],
    running: ["运行中", "#FF9500", "#FF950014"],
    waiting_tool: ["等待工具", "#FF9500", "#FF950014"],
    waiting_async_tool: ["等待异步", "#FF9500", "#FF950014"],
    completed: ["已完成", "#34C759", "#34C75914"],
    error: ["错误", "#FF3B30", "#FF3B3014"],
  };
  const [label, color, background] = styles[status] ?? [status, "#6E6E73", "#6E6E7314"];
  return (
    <span className="inline-flex rounded-full px-2 py-0.5" style={{ color, background, fontSize: 11, fontWeight: 600 }}>
      {label}
    </span>
  );
}

function ActionBadge({ actionType }: { actionType: string }) {
  const styles: Record<string, [string, string, string]> = {
    tool_call: ["工具调用", "#007AFF", "#007AFF14"],
    tool_result: ["工具结果", "#5856D6", "#5856D614"],
    final: ["最终回复", "#34C759", "#34C75914"],
    fallback: ["降级回复", "#FF9500", "#FF950014"],
    async_tool_submitted: ["异步提交", "#AF52DE", "#AF52DE14"],
    async_tool_completed: ["异步完成", "#34C759", "#34C75914"],
  };
  const [label, color, background] = styles[actionType] ?? [actionType, "#6E6E73", "#6E6E7314"];
  return (
    <span className="inline-flex rounded-full px-2 py-0.5" style={{ color, background, fontSize: 11, fontWeight: 600 }}>
      {label}
    </span>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="py-10 text-center" style={{ color: "#A1A1A6", fontSize: 13 }}>{text}</p>;
}

function ErrorText({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-1.5 py-3" style={{ color: "#FF3B30", fontSize: 12 }}>
      <AlertCircle size={13} />
      {text}
    </p>
  );
}

function LoadingText() {
  return (
    <div className="flex items-center justify-center gap-2 py-10" style={{ color: "#6E6E73", fontSize: 13 }}>
      <Loader2 size={14} className="animate-spin" />
      加载中
    </div>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (token: string, user: UserPublic) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(apiUrl(mode === "login" ? "/auth/login" : "/auth/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) throw new Error(await parseError(response));
      const data = await response.json() as AuthResponse;
      localStorage.setItem(TOKEN_KEY, data.token);
      onAuthenticated(data.token, data.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F5F5F7] px-4" style={{ fontFamily: APP_FONT }}>
      <div className="w-full max-w-[420px]">
        <div className="mb-9 text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-[24px] bg-[#007AFF] shadow-[0_16px_42px_rgba(0,122,255,0.28)]">
            <Sparkles size={28} color="#fff" />
          </div>
          <h1 style={{ color: "#1D1D1F", fontSize: 28, fontWeight: 750, letterSpacing: "-0.04em" }}>Multi-Session Agent</h1>
          <p className="mt-2" style={{ color: "#6E6E73", fontSize: 14 }}>登录后管理你的 Agent 对话</p>
        </div>

        <div className="rounded-[28px] border border-[#E5E5EA] bg-white p-7 shadow-[0_18px_60px_rgba(0,0,0,0.06)]">
          <div className="mb-6 grid grid-cols-2 rounded-2xl bg-[#F2F2F7] p-1">
            {(["login", "register"] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => { setMode(item); setError(null); }}
                className="rounded-xl py-2 transition"
                style={{
                  background: mode === item ? "#fff" : "transparent",
                  color: mode === item ? "#1D1D1F" : "#6E6E73",
                  boxShadow: mode === item ? "0 1px 8px rgba(0,0,0,0.08)" : "none",
                  fontSize: 14,
                  fontWeight: 700,
                }}
              >
                {item === "login" ? "登录" : "注册"}
              </button>
            ))}
          </div>

          <form className="space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="mb-1.5 block" style={{ color: "#6E6E73", fontSize: 12, fontWeight: 650 }}>用户名</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                className="w-full rounded-2xl border border-transparent bg-[#F2F2F7] px-4 py-3 outline-none transition focus:border-[#007AFF40] focus:bg-white focus:shadow-[0_0_0_4px_rgba(0,122,255,0.12)]"
                placeholder="alice"
                style={{ color: "#1D1D1F", fontSize: 14 }}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block" style={{ color: "#6E6E73", fontSize: 12, fontWeight: 650 }}>密码</span>
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                type="password"
                className="w-full rounded-2xl border border-transparent bg-[#F2F2F7] px-4 py-3 outline-none transition focus:border-[#007AFF40] focus:bg-white focus:shadow-[0_0_0_4px_rgba(0,122,255,0.12)]"
                placeholder="至少 8 位"
                style={{ color: "#1D1D1F", fontSize: 14 }}
              />
            </label>
            {error && <ErrorText text={error} />}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#007AFF] px-4 py-3 text-white transition hover:bg-[#0070E8] disabled:cursor-not-allowed disabled:opacity-40"
              style={{ fontSize: 14, fontWeight: 750 }}
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {mode === "login" ? "登录" : "创建账号"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function TodoPanel({ loading, error, todos }: { loading: boolean; error: string | null; todos: Todo[] }) {
  if (loading) return <LoadingText />;
  if (error) return <ErrorText text={error} />;
  if (!todos.length) return <EmptyState text="当前对话还没有待办。" />;

  return (
    <div className="divide-y divide-[#F2F2F7]">
      {todos.map((todo, index) => {
        const done = todo.status === "done";
        return (
          <div key={todo.id ?? `${todo.created_at}-${index}`} className="flex gap-3 py-3" style={{ opacity: done ? 0.52 : 1 }}>
            {done ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[#34C759]" /> : <Circle size={16} className="mt-0.5 shrink-0 text-[#C7C7CC]" />}
            <div className="min-w-0 flex-1">
              <p style={{ color: done ? "#6E6E73" : "#1D1D1F", fontSize: 13, lineHeight: 1.55, textDecoration: done ? "line-through" : "none" }}>
                {todo.content}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span className="rounded-full px-2 py-0.5" style={{ background: done ? "#34C75914" : "#FF950014", color: done ? "#34C759" : "#FF9500", fontSize: 11, fontWeight: 650 }}>
                  {done ? "已完成" : "待处理"}
                </span>
                {todo.due_time && <span style={{ color: "#6E6E73", fontSize: 11 }}>{todo.due_time}</span>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TraceRow({ trace, isLast }: { trace: Trace; isLast: boolean }) {
  const [open, setOpen] = useState(false);
  const hasDetails = !!trace.result_summary || !!trace.error || Object.keys(trace.arguments ?? {}).length > 0;
  return (
    <div className="relative flex gap-3">
      {!isLast && <div className="absolute bottom-0 left-[17px] top-9 w-px bg-[#E5E5EA]" />}
      <div className="relative z-10 flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-[#007AFF10]" style={{ color: "#007AFF", fontSize: 12, fontWeight: 750 }}>
        {trace.step}
      </div>
      <div className="min-w-0 flex-1 pb-5">
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <ActionBadge actionType={trace.action_type} />
          {trace.tool_name && (
            <span className="inline-flex items-center gap-1 rounded-md bg-[#F2F2F7] px-2 py-0.5" style={{ color: "#6E6E73", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 11 }}>
              <Terminal size={10} />
              {trace.tool_name}
            </span>
          )}
          <span className="inline-flex items-center gap-1" style={{ color: "#6E6E73", fontSize: 11 }}>
            <Clock size={10} />
            {trace.latency_ms} ms
          </span>
        </div>
        {trace.thought_summary && <p style={{ color: "#1D1D1F", fontSize: 13, lineHeight: 1.55 }}>{trace.thought_summary}</p>}
        {hasDetails && (
          <button type="button" onClick={() => setOpen((value) => !value)} className="mt-1.5 inline-flex items-center gap-1 text-[#007AFF] transition-opacity hover:opacity-65" style={{ fontSize: 12, fontWeight: 650 }}>
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {open ? "收起详情" : "展开详情"}
          </button>
        )}
        {open && (
          <div className="mt-2 space-y-2">
            {trace.result_summary && (
              <div className="rounded-xl border border-[#E5E5EA] bg-[#F8F8FA] p-3">
                <p className="mb-1" style={{ color: "#6E6E73", fontSize: 11, fontWeight: 650 }}>结果</p>
                <p style={{ color: "#1D1D1F", fontSize: 12, lineHeight: 1.5 }}>{trace.result_summary}</p>
              </div>
            )}
            {Object.keys(trace.arguments ?? {}).length > 0 && (
              <div className="rounded-xl border border-[#E5E5EA] bg-[#F8F8FA] p-3">
                <p className="mb-1" style={{ color: "#6E6E73", fontSize: 11, fontWeight: 650 }}>参数</p>
                <pre className="whitespace-pre-wrap break-all" style={{ color: "#1D1D1F", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 11 }}>
                  {JSON.stringify(trace.arguments, null, 2)}
                </pre>
              </div>
            )}
            {trace.error && <ErrorText text={trace.error} />}
          </div>
        )}
      </div>
    </div>
  );
}

function TracePanel({ loading, error, traces }: { loading: boolean; error: string | null; traces: Trace[] }) {
  if (loading) return <LoadingText />;
  if (error) return <ErrorText text={error} />;
  if (!traces.length) return <EmptyState text="发送消息后，这里会显示 Agent 的执行轨迹。" />;
  return <>{traces.map((trace, index) => <TraceRow key={trace.trace_id} trace={trace} isLast={index === traces.length - 1} />)}</>;
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [currentUser, setCurrentUser] = useState<UserPublic | null>(null);
  const [authChecking, setAuthChecking] = useState(!!token);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => localStorage.getItem(ACTIVE_SESSION_KEY));
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [input, setInput] = useState("");
  const [sendingSessionIds, setSendingSessionIds] = useState<Set<string>>(() => new Set());
  const [sendError, setSendError] = useState<string | null>(null);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [todosLoading, setTodosLoading] = useState(false);
  const [todosError, setTodosError] = useState<string | null>(null);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const activeSessionRef = useRef<string | null>(activeSessionId);
  const restoredSessionRef = useRef<string | null>(null);

  const apiFetch = useCallback(async (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(apiUrl(path), { ...init, headers });
    if (!response.ok) throw new Error(await parseError(response));
    return response;
  }, [token]);

  const loadSessions = useCallback(async () => {
    if (!token) return;
    setSessionsLoading(true);
    setSessionsError(null);
    try {
      const response = await apiFetch("/sessions");
      const data = await response.json() as { sessions: SessionSummary[] };
      setSessions(data.sessions);
    } catch (err) {
      setSessionsError((err as Error).message);
    } finally {
      setSessionsLoading(false);
    }
  }, [apiFetch, token]);

  const selectActiveSession = useCallback((sessionId: string | null) => {
    activeSessionRef.current = sessionId;
    setActiveSessionId(sessionId);
    if (sessionId) localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
    else localStorage.removeItem(ACTIVE_SESSION_KEY);
  }, []);

  const loadSession = useCallback(async (sessionId: string, knownSession?: SessionSummary) => {
    const showMessagesLoading = knownSession === undefined;
    restoredSessionRef.current = sessionId;
    if (activeSessionRef.current !== sessionId) selectActiveSession(sessionId);
    if (showMessagesLoading) setSidebarOpen(false);
    if (showMessagesLoading) setMessagesLoading(true);
    setSendError(null);
    if (showMessagesLoading) {
      setTodos([]);
      setTraces([]);
    }
    try {
      const [messageResponse, todoResponse, traceResponse] = await Promise.all([
        apiFetch(`/sessions/${encodeURIComponent(sessionId)}/messages`),
        apiFetch(`/sessions/${encodeURIComponent(sessionId)}/todos`),
        apiFetch(`/sessions/${encodeURIComponent(sessionId)}/trace`),
      ]);
      const messageData = await messageResponse.json() as { messages: MessageRecord[] };
      const todoData = await todoResponse.json() as { todos: Todo[] };
      const traceData = await traceResponse.json() as { traces: Trace[] };
      const session = knownSession ?? sessions.find((item) => item.session_id === sessionId);
      const restoredMessages = session
        ? restoreRunningSessionLoading(messageData.messages.map(toChatMessage), session)
        : messageData.messages.map(toChatMessage);
      setMessages(restoredMessages);
      if (session) {
        setSendingSessionIds((previous) => {
          const next = new Set(previous);
          if (isSessionRunning(session.status)) next.add(sessionId);
          else next.delete(sessionId);
          return next;
        });
      }
      setTodos(todoData.todos ?? []);
      setTraces(traceData.traces ?? []);
    } catch (err) {
      setSendError((err as Error).message);
    } finally {
      if (showMessagesLoading) setMessagesLoading(false);
    }
  }, [apiFetch, selectActiveSession, sessions]);

  const refreshDetails = useCallback(async (sessionId = activeSessionId) => {
    if (!sessionId) return;
    setTodosLoading(true);
    setTraceLoading(true);
    setTodosError(null);
    setTraceError(null);
    try {
      const [todoResponse, traceResponse] = await Promise.all([
        apiFetch(`/sessions/${encodeURIComponent(sessionId)}/todos`),
        apiFetch(`/sessions/${encodeURIComponent(sessionId)}/trace`),
      ]);
      const todoData = await todoResponse.json() as { todos: Todo[] };
      const traceData = await traceResponse.json() as { traces: Trace[] };
      setTodos(todoData.todos ?? []);
      setTraces(traceData.traces ?? []);
    } catch (err) {
      const message = (err as Error).message;
      setTodosError(message);
      setTraceError(message);
    } finally {
      setTodosLoading(false);
      setTraceLoading(false);
    }
  }, [activeSessionId, apiFetch]);

  const createNewSession = useCallback(async () => {
    const response = await apiFetch("/sessions", { method: "POST", body: JSON.stringify({}) });
    const data = await response.json() as { session: SessionSummary };
    setSessions((previous) => [data.session, ...previous.filter((session) => session.session_id !== data.session.session_id)]);
    selectActiveSession(data.session.session_id);
    setMessages([]);
    setTodos([]);
    setTraces([]);
    setSidebarOpen(false);
    return data.session.session_id;
  }, [apiFetch, selectActiveSession]);

  const submitMessage = useCallback(async () => {
    const content = input.trim();
    const initialSessionId = activeSessionId;
    const initialSendingKey = initialSessionId ?? PENDING_NEW_SESSION_ID;
    if (!content || sendingSessionIds.has(initialSendingKey)) return;

    setInput("");
    setSendError(null);
    setSendingSessionIds((previous) => new Set(previous).add(initialSendingKey));

    let sessionId = initialSessionId;
    let sendingKey = initialSendingKey;
    const loadingMessageId = newId("agent");
    try {
      if (!sessionId) {
        sessionId = await createNewSession();
        sendingKey = sessionId;
        setSendingSessionIds((previous) => {
          const next = new Set(previous);
          next.delete(PENDING_NEW_SESSION_ID);
          next.add(sessionId!);
          return next;
        });
      }

      const userMessage: ChatMessage = { id: newId("user"), role: "user", content, createdAt: new Date() };
      const loadingMessage: ChatMessage = { id: loadingMessageId, role: "agent", content: "", createdAt: new Date(), isLoading: true };
      if (activeSessionRef.current === sessionId) {
        setMessages((previous) => [...previous, userMessage, loadingMessage].slice(-MESSAGE_CACHE_LIMIT));
      }

      const response = await apiFetch(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      const data = await response.json() as { answer: string; session_status: string };
      if (activeSessionRef.current === sessionId) {
        setMessages((previous) => previous.map((message) => message.id === loadingMessageId
          ? { ...message, content: data.answer, sessionStatus: data.session_status, isLoading: false }
          : message));
      }
      await loadSessions();
      if (activeSessionRef.current === sessionId) await refreshDetails(sessionId);
    } catch (err) {
      if (activeSessionRef.current === sessionId) {
        setMessages((previous) => previous.filter((message) => message.id !== loadingMessageId));
        setSendError((err as Error).message);
      }
    } finally {
      setSendingSessionIds((previous) => {
        const next = new Set(previous);
        next.delete(initialSendingKey);
        next.delete(sendingKey);
        return next;
      });
    }
  }, [activeSessionId, apiFetch, createNewSession, input, loadSessions, refreshDetails, sendingSessionIds]);

  const logout = useCallback(async () => {
    try {
      if (token) await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Local logout should still clear invalid or unreachable sessions.
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ACTIVE_SESSION_KEY);
    activeSessionRef.current = null;
    restoredSessionRef.current = null;
    setToken(null);
    setCurrentUser(null);
    setSessions([]);
    setActiveSessionId(null);
    setMessages([]);
    setTodos([]);
    setTraces([]);
  }, [apiFetch, token]);

  const handleInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  };

  const pollRunningSession = useCallback(async (sessionId: string) => {
    if (!token) return;
    try {
      const response = await apiFetch("/sessions");
      const data = await response.json() as { sessions: SessionSummary[] };
      setSessions(data.sessions);
      const session = data.sessions.find((item) => item.session_id === sessionId);
      if (!session) {
        setSendingSessionIds((previous) => {
          const next = new Set(previous);
          next.delete(sessionId);
          return next;
        });
        return;
      }
      if (activeSessionRef.current === sessionId) {
        await loadSession(sessionId, session);
      } else if (!isSessionRunning(session.status)) {
        setSendingSessionIds((previous) => {
          const next = new Set(previous);
          next.delete(sessionId);
          return next;
        });
      }
    } catch (err) {
      if (activeSessionRef.current === sessionId) setSendError((err as Error).message);
    }
  }, [apiFetch, loadSession, token]);

  useEffect(() => {
    if (!token) {
      setAuthChecking(false);
      return;
    }
    apiFetch("/auth/me")
      .then((response) => response.json())
      .then((data: { user: UserPublic }) => setCurrentUser(data.user))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setCurrentUser(null);
      })
      .finally(() => setAuthChecking(false));
  }, [apiFetch, token]);

  useEffect(() => {
    if (currentUser) void loadSessions();
  }, [currentUser, loadSessions]);

  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    if (!currentUser || !sessions.length || restoredSessionRef.current === activeSessionId) return;
    const savedSessionId = localStorage.getItem(ACTIVE_SESSION_KEY);
    const nextSessionId = savedSessionId && sessions.some((session) => session.session_id === savedSessionId)
      ? savedSessionId
      : sessions[0]?.session_id;
    if (nextSessionId) void loadSession(nextSessionId);
  }, [activeSessionId, currentUser, loadSession, sessions]);

  const currentSessionSending = sendingSessionIds.has(activeSessionId ?? PENDING_NEW_SESSION_ID);

  useEffect(() => {
    if (!activeSessionId || !currentSessionSending) return;
    const intervalId = window.setInterval(() => {
      void pollRunningSession(activeSessionId);
    }, 1500);
    return () => window.clearInterval(intervalId);
  }, [activeSessionId, currentSessionSending, pollRunningSession]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.session_id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  );

  if (authChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F5F5F7]" style={{ fontFamily: APP_FONT, color: "#6E6E73" }}>
        <Loader2 size={18} className="mr-2 animate-spin" />
        正在恢复登录状态…
      </div>
    );
  }

  if (!currentUser || !token) {
    return <AuthScreen onAuthenticated={(nextToken, user) => { setToken(nextToken); setCurrentUser(user); }} />;
  }

  const Sidebar = (
    <aside className="flex h-full flex-col bg-[#F9F9F9]">
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#007AFF]">
            <Sparkles size={15} color="#fff" />
          </div>
          <span style={{ color: "#1D1D1F", fontSize: 14, fontWeight: 750 }}>Agent</span>
        </div>
        <button type="button" onClick={() => setSidebarOpen(false)} className="rounded-xl p-2 text-[#6E6E73] lg:hidden">
          <X size={18} />
        </button>
      </div>
      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={() => void createNewSession()}
          className="flex w-full items-center gap-2 rounded-2xl bg-[#007AFF] px-3 py-2.5 text-white transition hover:bg-[#0070E8]"
          style={{ fontSize: 14, fontWeight: 750 }}
        >
          <Plus size={16} />
          新对话
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2">
        {sessionsLoading && <LoadingText />}
        {sessionsError && <ErrorText text={sessionsError} />}
        {!sessionsLoading && !sessions.length && <EmptyState text="还没有对话。" />}
        {sessions.map((session) => {
          const active = session.session_id === activeSessionId;
          return (
            <button
              key={session.session_id}
              type="button"
              onClick={() => void loadSession(session.session_id)}
              className="mb-1 w-full rounded-2xl px-3 py-2.5 text-left transition hover:bg-[#F2F2F7]"
              style={{ background: active ? "#007AFF12" : "transparent" }}
            >
              <div className="flex items-center gap-2">
                <MessageSquare size={14} color={active ? "#007AFF" : "#6E6E73"} />
                <span className="min-w-0 flex-1 truncate" style={{ color: active ? "#007AFF" : "#1D1D1F", fontSize: 13, fontWeight: 700 }}>
                  {titleForSession(session)}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 pl-6">
                <span style={{ color: "#A1A1A6", fontSize: 11 }}>{relativeDate(session.updated_at)}</span>
                {session.message_count > 0 && <span style={{ color: "#A1A1A6", fontSize: 11 }}>{session.message_count} 条</span>}
              </div>
            </button>
          );
        })}
      </div>
      <div className="border-t border-[#E5E5EA] p-3">
        <div className="flex items-center gap-3 rounded-2xl bg-white p-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#007AFF] text-white" style={{ fontWeight: 750 }}>
            {currentUser.username.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate" style={{ color: "#1D1D1F", fontSize: 13, fontWeight: 750 }}>{currentUser.username}</p>
            <p className="truncate" style={{ color: "#A1A1A6", fontSize: 11 }}>已登录</p>
          </div>
          <button type="button" onClick={() => void logout()} className="rounded-xl p-2 text-[#6E6E73] transition hover:bg-[#F2F2F7] hover:text-[#FF3B30]" title="退出登录">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="h-screen overflow-hidden bg-[#FFFFFF] text-[#1D1D1F]" style={{ fontFamily: APP_FONT }}>
      <div className="flex h-full">
        <div className="hidden h-full w-[280px] shrink-0 border-r border-[#E5E5EA] lg:block">
          {Sidebar}
        </div>
        {sidebarOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={() => setSidebarOpen(false)} />
            <div className="relative h-full w-[286px] shadow-2xl">{Sidebar}</div>
          </div>
        )}

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5EA] px-4">
            <div className="flex min-w-0 items-center gap-2">
              <button type="button" onClick={() => setSidebarOpen(true)} className="rounded-xl p-2 text-[#6E6E73] lg:hidden">
                <Menu size={18} />
              </button>
              <h1 className="truncate" style={{ color: "#1D1D1F", fontSize: 15, fontWeight: 750 }}>
                {activeSession ? titleForSession(activeSession) : "Multi-Session Agent"}
              </h1>
              {activeSession && <StatusBadge status={activeSession.status} />}
            </div>
            <button type="button" onClick={() => setDetailsOpen((value) => !value)} className="hidden items-center gap-1 rounded-2xl bg-[#F2F2F7] px-3 py-2 text-[#6E6E73] transition hover:bg-[#E5E5EA] md:inline-flex" style={{ fontSize: 12, fontWeight: 700 }}>
              {detailsOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
              Session details
            </button>
          </header>

          <div className="flex min-h-0 flex-1">
            <section className="flex min-w-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-8">
                {messagesLoading ? <LoadingText /> : messages.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center text-center">
                    <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-[24px] bg-[#F2F2F7]">
                      <Sparkles size={28} color="#A1A1A6" />
                    </div>
                    <h2 style={{ color: "#1D1D1F", fontSize: 26, fontWeight: 750, letterSpacing: "-0.04em" }}>
                      今天想让 Agent 做什么？
                    </h2>
                    <p className="mt-2 max-w-[440px]" style={{ color: "#6E6E73", fontSize: 14, lineHeight: 1.6 }}>
                      输入消息即可开始新对话，也可以从左侧选择已有 session 继续。
                    </p>
                  </div>
                ) : (
                  <div className="mx-auto max-w-3xl space-y-5">
                    {messages.map((message) => {
                      const user = message.role === "user";
                      return (
                        <div key={message.id} className={`flex ${user ? "justify-end" : "justify-start"}`}>
                          {!user && <div className="mr-3 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#007AFF]"><Sparkles size={14} color="#fff" /></div>}
                          <div className={`flex max-w-[78%] flex-col ${user ? "items-end" : "items-start"}`}>
                            <div className="px-4 py-2.5" style={{ background: user ? "#007AFF" : "#F2F2F7", borderRadius: user ? "20px 20px 6px 20px" : "20px 20px 20px 6px", color: user ? "#fff" : "#1D1D1F", fontSize: 14, lineHeight: 1.65, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                              {message.isLoading ? <span className="inline-flex items-center gap-2 text-[#6E6E73]"><Loader2 size={14} className="animate-spin" />Agent 正在运行…</span> : message.content}
                            </div>
                            <div className="mt-1 flex items-center gap-2 px-1">
                              <span style={{ color: "#A1A1A6", fontSize: 11 }}>{message.createdAt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>
                              {message.sessionStatus && <StatusBadge status={message.sessionStatus} />}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    <div ref={chatEndRef} />
                  </div>
                )}
              </div>
              {sendError && <div className="mx-auto w-full max-w-3xl px-4"><ErrorText text={sendError} /></div>}
              <div className="shrink-0 border-t border-[#F2F2F7] px-4 py-4">
                <div className="mx-auto flex max-w-3xl items-end gap-2">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={handleInputKeyDown}
                    disabled={currentSessionSending}
                    rows={1}
                    placeholder="给 Agent 发送消息"
                    className="max-h-[140px] min-h-[50px] flex-1 resize-none rounded-[24px] border border-[#E5E5EA] bg-white px-4 py-3 outline-none transition focus:border-[#007AFF40] focus:shadow-[0_0_0_4px_rgba(0,122,255,0.12)]"
                    style={{ color: "#1D1D1F", fontSize: 14, lineHeight: 1.45 }}
                  />
                  <button type="button" onClick={() => void submitMessage()} disabled={!input.trim() || currentSessionSending} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#007AFF] text-white transition hover:bg-[#0070E8] disabled:cursor-not-allowed disabled:opacity-35" aria-label="发送">
                    {currentSessionSending ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
                  </button>
                </div>
              </div>
            </section>

            {detailsOpen && (
              <aside className="hidden w-[360px] shrink-0 border-l border-[#E5E5EA] bg-white md:flex md:flex-col">
                <div className="flex items-center justify-between border-b border-[#E5E5EA] px-5 py-4">
                  <span style={{ color: "#1D1D1F", fontSize: 14, fontWeight: 750 }}>Session details</span>
                  <button type="button" onClick={() => void refreshDetails()} className="inline-flex items-center gap-1 text-[#007AFF]" style={{ fontSize: 12, fontWeight: 700 }}>
                    <RefreshCw size={12} />刷新
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <div className="border-b border-[#E5E5EA] px-5 py-4">
                    <p className="mb-3" style={{ color: "#1D1D1F", fontSize: 13, fontWeight: 750 }}>Todos</p>
                    <TodoPanel loading={todosLoading} error={todosError} todos={todos} />
                  </div>
                  <div className="px-5 py-4">
                    <p className="mb-3" style={{ color: "#1D1D1F", fontSize: 13, fontWeight: 750 }}>Trace</p>
                    <TracePanel loading={traceLoading} error={traceError} traces={traces} />
                  </div>
                </div>
              </aside>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
