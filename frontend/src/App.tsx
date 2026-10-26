import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  FileText,
  GitBranch,
  Inbox,
  Layers3,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  MessageSquare,
  PanelRightClose,
  Plus,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Ticket as TicketIcon,
  WandSparkles,
  X,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, setToken, streamChat } from "./api";
import type {
  Conversation,
  Dashboard,
  Document,
  Draft,
  Message,
  Run,
  Source,
  Ticket,
  Trace,
  User,
} from "./types";

const STATUS: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  waiting: "待补充",
  resolved: "已解决",
  closed: "已关闭",
};
const PRIORITY: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  urgent: "紧急",
};
const TOOLS: Record<string, string> = {
  search_knowledge: "检索运维知识",
  inspect_log: "分析日志线索",
  query_service_status: "查询演示监控",
  draft_ticket: "整理工单草稿",
  get_ticket: "查询工单",
};
const TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "closed"],
  in_progress: ["waiting", "resolved", "open"],
  waiting: ["in_progress", "resolved"],
  resolved: ["closed", "in_progress"],
  closed: [],
};
type Page = "dashboard" | "assistant" | "tickets" | "knowledge" | "runs";
type Notify = (message: string) => void;
const NAV: { id: Page; label: string; icon: LucideIcon }[] = [
  { id: "dashboard", label: "工作台", icon: LayoutDashboard },
  { id: "assistant", label: "AI 支持助手", icon: Sparkles },
  { id: "tickets", label: "工单中心", icon: TicketIcon },
  { id: "knowledge", label: "知识库", icon: BookOpen },
  { id: "runs", label: "运行记录", icon: Activity },
];

function date(value: string, full = false) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    ...(full ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
}
function useLoad<T>(path: string, revision = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<T>(path)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((reason) => {
        if (active) setError(reason.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, revision]);
  return { data, error, loading };
}
function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={"brand-mark " + (small ? "small" : "")}>
      <GitBranch size={small ? 17 : 23} strokeWidth={2.5} />
    </span>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status}>
      <i />
      {STATUS[status] || status}
    </span>
  );
}
function Priority({ value }: { value: string }) {
  return (
    <span className={"priority " + value}>
      <span>
        {value === "urgent"
          ? "!!!"
          : value === "high"
            ? "↑"
            : value === "medium"
              ? "＝"
              : "↓"}
      </span>
      {PRIORITY[value]}
    </span>
  );
}
function Empty({
  title = "这里还没有记录",
  description = "完成一次操作后，相关内容会显示在这里。",
  icon: Icon = Inbox,
}: {
  title?: string;
  description?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="empty">
      <span>
        <Icon size={27} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
function ErrorBox({ message }: { message: string }) {
  return message ? <div className="error-box">{message}</div> : null;
}
function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={22} />
      <span>正在加载…</span>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="关闭窗口" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("engineer@supportflow.local"),
    [password, setPassword] = useState("SupportFlow123!"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const { data: health } = useLoad<{
    demo_enabled: boolean;
    agent_mode: string;
  }>("/health");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ access_token: string; user: User }>(
        "/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) },
      );
      setToken(result.access_token);
      onLogin(result.user);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="login-brand">
          <Mark />
          <b>SupportFlow</b>
        </div>
        <div className="story-copy">
          <span className="eyebrow light">TECHNICAL SUPPORT, CONNECTED.</span>
          <h1>
            从一个问题，
            <br />
            到一次解决。
          </h1>
          <p>
            让知识、AI 与团队协作连接起来，
            <br />
            为每一次技术支持找到清晰的下一步。
          </p>
          <div className="story-steps">
            <span>
              <BookOpen size={18} />
              找到依据
            </span>
            <ChevronRight size={16} />
            <span>
              <Sparkles size={18} />
              辅助排障
            </span>
            <ChevronRight size={16} />
            <span>
              <CheckCircle2 size={18} />
              协作解决
            </span>
          </div>
        </div>
        <div className="story-footer">
          <span className="status-dot" />
          SupportFlow · 技术支持与工单协作平台
        </div>
        <div className="story-ring ring-one" />
        <div className="story-ring ring-two" />
      </div>
      <div className="login-form-wrap">
        <form className="login-form" onSubmit={submit}>
          <span className="eyebrow">YOUR SUPPORT WORKSPACE</span>
          <h2>欢迎回到工作台</h2>
          <p className="muted">登录后，继续跟进问题与团队协作。</p>
          <label>
            工作邮箱
            <input
              autoComplete="username"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            密码
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <ErrorBox message={error} />
          <button className="button primary login-submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={17} /> : null}
            进入工作台
            <ArrowRight size={17} />
          </button>
          {health?.demo_enabled && (
            <div className="demo-login">
              <div>
                <span className="tiny-pill">本地演示</span>
                <span>选择一个角色体验</span>
              </div>
              <div className="demo-roles">
                {[
                  ["engineer", "支持工程师"],
                  ["customer", "提问用户"],
                  ["admin", "管理员"],
                ].map(([role, label]) => (
                  <button
                    type="button"
                    key={role}
                    className={email.startsWith(role + "@") ? "active" : ""}
                    onClick={() => {
                      setEmail(role + "@supportflow.local");
                      setPassword("SupportFlow123!");
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p>演示密码：SupportFlow123!</p>
            </div>
          )}
          <div className="login-note">
            <ShieldCheck size={15} />
            会话与工单均按当前账号权限访问
          </div>
        </form>
      </div>
    </div>
  );
}

function TicketTable({
  tickets,
  onSelect,
}: {
  tickets: Ticket[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table className="tickets-table">
        <thead>
          <tr>
            <th>工单 / 问题</th>
            <th>状态</th>
            <th>优先级</th>
            <th>处理人</th>
            <th>更新于</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id} onClick={() => onSelect(ticket.id)}>
              <td>
                <button
                  className="ticket-title"
                  onClick={() => onSelect(ticket.id)}
                >
                  {ticket.title}
                </button>
                <span className="ticket-sub">
                  {ticket.number}
                  <span>·</span>
                  {ticket.category}
                </span>
              </td>
              <td>
                <Badge status={ticket.status} />
              </td>
              <td>
                <Priority value={ticket.priority} />
              </td>
              <td>
                {ticket.assignee_name ? (
                  <span className="person">
                    <i>{ticket.assignee_name.slice(-2)}</i>
                    {ticket.assignee_name}
                  </span>
                ) : (
                  <span className="muted">未分派</span>
                )}
              </td>
              <td className="muted nowrap">{date(ticket.updated_at)}</td>
              <td>
                <ChevronRight size={16} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DashboardPage({
  user,
  revision,
  navigate,
  onTicket,
}: {
  user: User;
  revision: number;
  navigate: (page: Page, prompt?: string) => void;
  onTicket: (id: string) => void;
}) {
  const { data, error, loading } = useLoad<Dashboard>("/dashboard", revision);
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox message={error} />;
  const cards = [
    {
      label: "全部工单",
      value: data.total,
      icon: TicketIcon,
      note: "当前账号可访问的工单",
      color: "slate",
    },
    {
      label: "待处理",
      value: data.counts.open,
      icon: Inbox,
      note: "等待团队接手",
      color: "amber",
    },
    {
      label: "处理中",
      value: data.counts.in_progress,
      icon: Activity,
      note: "正在推进解决",
      color: "blue",
    },
    {
      label: "已解决",
      value: data.counts.resolved + data.counts.closed,
      icon: CheckCircle2,
      note: "已解决及已关闭",
      color: "green",
    },
  ];
  return (
    <div className="page dashboard-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">SUPPORT OVERVIEW</span>
          <h1>
            {user.name}，工作顺利。<span className="greeting-spark">✳</span>
          </h1>
          <p>从这里了解支持进展，让每个问题都有回应。</p>
        </div>
        <span className="date-chip">
          <Clock3 size={15} />
          {new Intl.DateTimeFormat("zh-CN", {
            timeZone: "Asia/Shanghai",
            year: "numeric",
            month: "long",
            day: "numeric",
            weekday: "short",
          }).format(new Date())}
        </span>
      </div>
      <ErrorBox message={error} />
      <div className="stats-grid">
        {cards.map(({ label, value, icon: Icon, note, color }) => (
          <div className="stat-card" key={label}>
            <div className="stat-top">
              <span>{label}</span>
              <span className={"stat-icon " + color}>
                <Icon size={19} />
              </span>
            </div>
            <strong>{value.toString().padStart(2, "0")}</strong>
            <p>{note}</p>
          </div>
        ))}
      </div>
      <div className="assist-banner">
        <div className="banner-orb">
          <Sparkles size={28} />
        </div>
        <div>
          <span className="eyebrow">YOUR AI SUPPORT PARTNER</span>
          <h2>先问问 AI，让排查更有方向。</h2>
          <p>结合知识依据与日志线索，整理排查步骤，需要时一键转为工单。</p>
        </div>
        <button className="button light" onClick={() => navigate("assistant")}>
          开始一次诊断
          <ArrowUpRight size={17} />
        </button>
      </div>
      <div className="dashboard-columns">
        <section className="panel recent-panel">
          <div className="panel-title">
            <div>
              <h2>
                最近更新的工单 <span className="count">{data.total}</span>
              </h2>
              <p>持续跟进，直到问题得到解决</p>
            </div>
            <button className="text-button" onClick={() => navigate("tickets")}>
              查看全部
              <ArrowRight size={15} />
            </button>
          </div>
          {data.recent_tickets.length ? (
            <TicketTable tickets={data.recent_tickets} onSelect={onTicket} />
          ) : (
            <Empty
              title="还没有工单"
              description="可以先向 AI 描述问题，或在工单中心创建。"
            />
          )}
        </section>
        <div className="dashboard-side">
          <section className="panel distribution">
            <div className="panel-title">
              <h2>处理概览</h2>
              <Layers3 size={18} />
            </div>
            <div className="distribution-track">
              {Object.entries(data.counts).map(([status, count]) =>
                count > 0 ? (
                  <span
                    className={"segment " + status}
                    key={status}
                    style={{ flex: count }}
                    title={`${STATUS[status]} ${count}`}
                  />
                ) : null,
              )}
            </div>
            {Object.entries(data.counts).map(([status, count]) => (
              <div className="distribution-row" key={status}>
                <span>
                  <i className={"dot " + status} />
                  {STATUS[status]}
                </span>
                <b>{count}</b>
              </div>
            ))}
          </section>
          <section className="panel quick-panel">
            <div className="panel-title">
              <h2>常用排查</h2>
              <WandSparkles size={18} />
            </div>
            {[
              "FastAPI 部署后出现 502",
              "数据库连接池耗尽怎么办",
              "Docker 容器无法连接数据库",
            ].map((text, index) => (
              <button key={text} onClick={() => navigate("assistant", text)}>
                <span>0{index + 1}</span>
                {text}
                <ArrowUpRight size={15} />
              </button>
            ))}
            <div className="knowledge-foot">
              <BookOpen size={15} />
              {data.knowledge_count} 份团队知识可供检索
            </div>
          </section>
        </div>
      </div>
      <div className="workspace-foot">
        <span>
          <span className="status-dot" />
          所有数据来自当前工作区
        </span>
        <span>更清晰的支持，更顺畅的协作。</span>
      </div>
    </div>
  );
}

function DraftPreview({
  draft,
  onConfirm,
  busy = false,
}: {
  draft: Draft;
  onConfirm: () => void;
  busy?: boolean;
}) {
  return (
    <div className="draft-preview">
      <div className="draft-top">
        <span className="draft-symbol">
          <TicketIcon size={19} />
        </span>
        <div>
          <strong>工单草稿已就绪</strong>
          <p>检查内容后，由你确认创建</p>
        </div>
        <span className="tiny-pill">待确认</span>
      </div>
      <h3>{draft.title}</h3>
      <div className="draft-tags">
        <Priority value={draft.priority} />
        <span>{draft.category}</span>
      </div>
      <details>
        <summary>
          查看完整描述
          <ChevronDown size={14} />
        </summary>
        <div className="plain-content">{draft.description}</div>
      </details>
      <button className="button primary" disabled={busy} onClick={onConfirm}>
        {busy ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <Check size={16} />
        )}
        确认创建工单
      </button>
      <span className="draft-note">确认前不会生成正式工单</span>
    </div>
  );
}

function NewTicketModal({
  onClose,
  onCreated,
  notify,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
  notify: Notify;
}) {
  const [draft, setDraft] = useState<Draft | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      setDraft(
        await api<Draft>("/drafts", {
          method: "POST",
          body: JSON.stringify(Object.fromEntries(form)),
        }),
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!draft) return;
    setBusy(true);
    try {
      const ticket = await api<Ticket>(`/drafts/${draft.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: "draft-" + draft.id }),
      });
      notify("工单已创建，团队可以开始跟进");
      onCreated(ticket.id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={draft ? "确认工单内容" : "创建技术支持工单"}
      onClose={onClose}
    >
      <ErrorBox message={error} />
      {draft ? (
        <DraftPreview draft={draft} onConfirm={confirm} busy={busy} />
      ) : (
        <form className="stack-form" onSubmit={preview}>
          <label>
            问题标题
            <input
              name="title"
              placeholder="简要描述遇到的问题"
              minLength={3}
              maxLength={160}
              required
            />
          </label>
          <div className="form-row">
            <label>
              问题分类
              <select name="category">
                <option>部署与运行</option>
                <option>数据库</option>
                <option>容器与网络</option>
                <option>API 与鉴权</option>
                <option>其他咨询</option>
              </select>
            </label>
            <label>
              优先级
              <select name="priority" defaultValue="medium">
                {Object.entries(PRIORITY).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            问题描述
            <textarea
              name="description"
              rows={8}
              placeholder="期望行为、实际行为、影响范围、版本与脱敏日志…"
              minLength={10}
              maxLength={20000}
              required
            />
          </label>
          <p className="form-hint">请在提交前去除密码、API key 等凭据。</p>
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <ArrowRight size={16} />
            )}
            预览工单
          </button>
        </form>
      )}
    </Modal>
  );
}

function TicketsPage({
  revision,
  onTicket,
  onNew,
  notify,
}: {
  revision: number;
  onTicket: (id: string) => void;
  onNew: () => void;
  notify: Notify;
}) {
  const [status, setStatus] = useState(""),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [draftOpen, setDraftOpen] = useState<Draft | null>(null),
    [refresh, setRefresh] = useState(0),
    [busy, setBusy] = useState(false);
  const { data, error, loading } = useLoad<{
    items: Ticket[];
    total: number;
    page_size: number;
  }>(
    `/tickets?status=${status}&q=${encodeURIComponent(q)}&page=${page}`,
    revision + refresh,
  );
  const { data: drafts } = useLoad<Draft[]>("/drafts", revision + refresh);
  async function confirm() {
    if (!draftOpen) return;
    setBusy(true);
    try {
      const ticket = await api<Ticket>(`/drafts/${draftOpen.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: "draft-" + draftOpen.id }),
      });
      setDraftOpen(null);
      setRefresh((v) => v + 1);
      notify("工单已创建");
      onTicket(ticket.id);
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">TICKET COLLABORATION</span>
          <h1>工单中心</h1>
          <p>把问题交给团队，把进展留在记录里。</p>
        </div>
        <button className="button primary" onClick={onNew}>
          <Plus size={17} />
          新建工单
        </button>
      </div>
      {drafts && drafts.length > 0 && (
        <div className="pending-drafts">
          <span>
            <TicketIcon size={17} />
            <b>{drafts.length} 份草稿待确认</b>
          </span>
          <div>
            {drafts.slice(0, 3).map((draft) => (
              <button key={draft.id} onClick={() => setDraftOpen(draft)}>
                {draft.title}
                <ArrowUpRight size={14} />
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="panel">
        <div className="ticket-toolbar">
          <div className="tabs">
            {[
              ["", "全部工单"],
              ["open", "待处理"],
              ["in_progress", "处理中"],
              ["waiting", "待补充"],
              ["resolved", "已解决"],
              ["closed", "已关闭"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={status === value ? "active" : ""}
                onClick={() => {
                  setStatus(value);
                  setPage(1);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="search-input">
            <Search size={16} />
            <input
              aria-label="搜索工单"
              placeholder="搜索标题或编号"
              value={q}
              onChange={(event) => {
                setQ(event.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <ErrorBox message={error} />
        {loading && !data ? (
          <Loading />
        ) : data?.items.length ? (
          <TicketTable tickets={data.items} onSelect={onTicket} />
        ) : (
          <Empty
            title="没有找到工单"
            description="试试其他筛选条件，或创建一份新的工单。"
          />
        )}
        <div className="table-footer">
          <span>
            共 {data?.total || 0} 条工单 · 第 {page} 页
          </span>
          <div>
            <button
              className="icon-button"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              aria-label="上一页"
            >
              <ArrowLeft size={16} />
            </button>
            <button
              className="icon-button"
              disabled={!data || page * 20 >= data.total}
              onClick={() => setPage((p) => p + 1)}
              aria-label="下一页"
            >
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
      {draftOpen && (
        <Modal title="确认工单草稿" onClose={() => setDraftOpen(null)}>
          <DraftPreview draft={draftOpen} onConfirm={confirm} busy={busy} />
        </Modal>
      )}
    </div>
  );
}

function TicketDetail({
  id,
  user,
  onClose,
  onChanged,
  notify,
}: {
  id: string;
  user: User;
  onClose: () => void;
  onChanged: () => void;
  notify: Notify;
}) {
  const [revision, setRevision] = useState(0),
    [comment, setComment] = useState(""),
    [busy, setBusy] = useState(false);
  const { data: ticket, error } = useLoad<Ticket>("/tickets/" + id, revision),
    { data: people } = useLoad<User[]>("/users");
  async function update(changes: Record<string, unknown>) {
    if (!ticket) return;
    setBusy(true);
    try {
      await api("/tickets/" + id, {
        method: "PATCH",
        body: JSON.stringify({ version: ticket.version, ...changes }),
      });
      notify("工单已更新");
      onChanged();
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setRevision((v) => v + 1);
      setBusy(false);
    }
  }
  async function addComment(event: FormEvent) {
    event.preventDefault();
    if (!comment.trim()) return;
    setBusy(true);
    try {
      await api("/tickets/" + id + "/comments", {
        method: "POST",
        body: JSON.stringify({ content: comment }),
      });
      setComment("");
      setRevision((v) => v + 1);
      onChanged();
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal wide title={ticket?.number || "工单详情"} onClose={onClose}>
      <ErrorBox message={error} />
      {!ticket ? (
        <Loading />
      ) : (
        <>
          <div className="ticket-detail-title">
            <Badge status={ticket.status} />
            <Priority value={ticket.priority} />
            <h2>{ticket.title}</h2>
            <p>
              {ticket.owner_name} 提交于 {date(ticket.created_at, true)} ·{" "}
              {ticket.category}
            </p>
          </div>
          {user.role !== "requester" && (
            <div className="ticket-controls">
              <label>
                状态
                <select
                  value={ticket.status}
                  disabled={busy}
                  onChange={(event) =>
                    void update({ status: event.target.value })
                  }
                >
                  {[ticket.status, ...TRANSITIONS[ticket.status]].map(
                    (status) => (
                      <option key={status} value={status}>
                        {STATUS[status]}
                      </option>
                    ),
                  )}
                </select>
              </label>
              <label>
                处理人
                <select
                  value={ticket.assignee_id || ""}
                  disabled={busy}
                  onChange={(event) =>
                    void update({ assignee_id: event.target.value || null })
                  }
                >
                  <option value="">未分派</option>
                  {people?.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                优先级
                <select
                  value={ticket.priority}
                  disabled={busy}
                  onChange={(event) =>
                    void update({ priority: event.target.value })
                  }
                >
                  {Object.entries(PRIORITY).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
          <section className="detail-section">
            <h3>
              <FileText size={16} />
              问题描述
            </h3>
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {ticket.description}
              </ReactMarkdown>
            </div>
          </section>
          <section className="detail-section">
            <h3>
              <MessageSquare size={16} />
              协作讨论{" "}
              <span className="count">{ticket.comments?.length || 0}</span>
            </h3>
            {ticket.comments?.map((item) => (
              <div className="comment" key={item.id}>
                <span className="avatar mini">
                  {item.author_name.slice(-2)}
                </span>
                <div>
                  <div className="comment-author">
                    <b>{item.author_name}</b>
                    <time>{date(item.created_at, true)}</time>
                  </div>
                  <p>{item.content}</p>
                </div>
              </div>
            ))}
            <form className="comment-form" onSubmit={addComment}>
              <textarea
                aria-label="处理意见"
                placeholder="补充信息，或记录你的处理意见…"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                maxLength={5000}
                rows={3}
                required
              />
              <button
                className="button primary small"
                disabled={busy || !comment.trim()}
              >
                <Send size={14} />
                发送回复
              </button>
            </form>
          </section>
          <section className="detail-section">
            <h3>
              <GitBranch size={16} />
              操作时间线
            </h3>
            <div className="timeline">
              {ticket.events?.map((event) => (
                <div key={event.id}>
                  <i />
                  <p>
                    <b>{event.actor_name}</b>{" "}
                    {event.action === "created"
                      ? "创建了工单"
                      : event.action === "commented"
                        ? "补充了处理意见"
                        : "更新了工单"}
                    <time>{date(event.created_at, true)}</time>
                  </p>
                  {event.action === "updated" && (
                    <span>{formatEvent(event.detail)}</span>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </Modal>
  );
}
function formatEvent(detail: string) {
  try {
    const changes = JSON.parse(detail) as Record<
      string,
      { from: string; to: string }
    >;
    return Object.entries(changes)
      .map(
        ([key, value]) =>
          `${key === "status" ? "状态" : key === "priority" ? "优先级" : "处理人"}：${STATUS[value.from] || PRIORITY[value.from] || value.from || "未分派"} → ${STATUS[value.to] || PRIORITY[value.to] || value.to || "未分派"}`,
      )
      .join("；");
  } catch {
    return detail;
  }
}

function DocumentModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error } = useLoad<Document>("/knowledge/" + id);
  return (
    <Modal wide title={data?.title || "知识文档"} onClose={onClose}>
      <ErrorBox message={error} />
      {data ? (
        <>
          <div className="document-meta">
            <span className="product-tag">{data.product}</span>
            <span>{data.version}</span>
            <span>{data.source}</span>
          </div>
          <div className="markdown document-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {data.content || ""}
            </ReactMarkdown>
          </div>
        </>
      ) : (
        <Loading />
      )}
    </Modal>
  );
}

function KnowledgePage({ user, notify }: { user: User; notify: Notify }) {
  const [revision, setRevision] = useState(0),
    [query, setQuery] = useState(""),
    [results, setResults] = useState<Source[] | null>(null),
    [opened, setOpened] = useState(""),
    [adding, setAdding] = useState(false),
    [busy, setBusy] = useState(false),
    [content, setContent] = useState("");
  const { data: documents, error } = useLoad<Document[]>(
    "/knowledge",
    revision,
  );
  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setBusy(true);
    try {
      setResults(
        (
          await api<{ items: Source[] }>(
            "/knowledge/search?q=" + encodeURIComponent(query),
          )
        ).items,
      );
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await api("/knowledge", {
        method: "POST",
        body: JSON.stringify({ ...Object.fromEntries(form), content }),
      });
      setAdding(false);
      setContent("");
      setRevision((v) => v + 1);
      setResults(null);
      notify("文档已入库，可立即检索");
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">TEAM KNOWLEDGE</span>
          <h1>让经验，成为下一次的答案。</h1>
          <p>维护团队运维知识，为 AI 回答提供可追溯的依据。</p>
        </div>
        {user.role !== "requester" && (
          <button className="button primary" onClick={() => setAdding(true)}>
            <Plus size={17} />
            添加知识
          </button>
        )}
      </div>
      <div className="knowledge-search panel">
        <div className="knowledge-search-icon">
          <BookOpen size={22} />
        </div>
        <form onSubmit={search}>
          <input
            aria-label="检索知识库"
            placeholder="描述问题，检索相关的排查经验…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!event.target.value) setResults(null);
            }}
          />
          <button className="button primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Search size={16} />
            )}
            检索知识
          </button>
        </form>
        <span>BM25 关键词检索 · 支持中文与英文</span>
      </div>
      <ErrorBox message={error} />
      <div className="section-label">
        <h2>
          {results ? "检索结果" : "全部知识"}{" "}
          <span className="count">
            {results ? results.length : documents?.length || 0}
          </span>
        </h2>
        <span>
          {results ? "按相关度排序" : "共享团队资料 · 内置资料为自编教学内容"}
        </span>
      </div>
      {results ? (
        <div className="search-results">
          {results.length ? (
            results.map((item) => (
              <button
                className="panel result-card"
                key={item.chunk_id}
                onClick={() => setOpened(item.document_id)}
              >
                <div>
                  <span className="product-tag">{item.product}</span>
                  <span className="muted">相关度 {item.score.toFixed(2)}</span>
                </div>
                <h3>
                  {item.title}
                  <ArrowUpRight size={16} />
                </h3>
                <p>{item.content.slice(0, 250)}</p>
                <small>
                  {item.heading} · {item.version}
                </small>
              </button>
            ))
          ) : (
            <Empty
              title="没有找到匹配内容"
              description="试试产品名、错误码或日志里的关键词。"
            />
          )}
        </div>
      ) : (
        <div className="knowledge-grid">
          {documents?.map((document, index) => (
            <button
              className="panel document-card"
              key={document.id}
              onClick={() => setOpened(document.id)}
            >
              <div className="document-card-top">
                <span className={"document-symbol tone-" + (index % 4)}>
                  <FileText size={24} />
                </span>
                <ArrowUpRight size={17} />
              </div>
              <span className="product-tag">{document.product}</span>
              <h3>{document.title}</h3>
              <p>{document.source}</p>
              <div className="document-card-foot">
                <span>
                  {document.characters.toLocaleString()} 字符 ·{" "}
                  {document.version}
                </span>
                <span>{date(document.created_at)}</span>
              </div>
            </button>
          ))}
        </div>
      )}
      {opened && <DocumentModal id={opened} onClose={() => setOpened("")} />}{" "}
      {adding && (
        <Modal title="添加团队知识" onClose={() => setAdding(false)}>
          <form className="stack-form" onSubmit={add}>
            <label>
              文档标题
              <input name="title" minLength={3} maxLength={200} required />
            </label>
            <div className="form-row">
              <label>
                产品
                <input
                  name="product"
                  placeholder="例如 FastAPI"
                  required
                  maxLength={80}
                />
              </label>
              <label>
                版本
                <input
                  name="version"
                  defaultValue="通用"
                  required
                  maxLength={40}
                />
              </label>
            </div>
            <label>
              来源说明
              <input
                name="source"
                defaultValue="团队知识库"
                required
                maxLength={500}
              />
            </label>
            <label>
              正文（Markdown 或纯文本）
              <textarea
                rows={10}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                minLength={20}
                maxLength={60000}
                required
              />
            </label>
            <label className="file-picker">
              <FileText size={16} />
              或读取本地 .md / .txt 文件
              <input
                type="file"
                accept=".md,.txt"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    if (file.size > 240000) {
                      notify("文件过大，请控制在 6 万字符内");
                      return;
                    }
                    setContent((await file.text()).slice(0, 60000));
                  }
                }}
              />
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Plus size={16} />
              )}
              保存并加入检索
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function AssistantPage({
  initialPrompt,
  clearPrompt,
  notify,
  onTicket,
  onChanged,
}: {
  initialPrompt: string;
  clearPrompt: () => void;
  notify: Notify;
  onTicket: (id: string) => void;
  onChanged: () => void;
}) {
  const [conversationId, setConversationId] = useState(""),
    [messages, setMessages] = useState<Message[]>([]),
    [input, setInput] = useState(initialPrompt),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [traces, setTraces] = useState<Trace[]>([]),
    [status, setStatus] = useState(""),
    [revision, setRevision] = useState(0),
    [sourceOpen, setSourceOpen] = useState(""),
    [sideOpen, setSideOpen] = useState(true),
    [confirming, setConfirming] = useState("");
  const { data: conversations } = useLoad<Conversation[]>(
    "/conversations",
    revision,
  );
  const endRef = useRef<HTMLDivElement>(null);
  const latest = messages
    .filter((message) => message.role === "assistant")
    .at(-1);
  const sources = latest?.metadata?.sources || [];
  const tools = busy ? traces : latest?.metadata?.traces || [];
  useEffect(() => {
    if (initialPrompt) {
      setInput(initialPrompt);
      clearPrompt();
    }
  }, [initialPrompt, clearPrompt]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy, traces]);
  async function selectConversation(id: string) {
    if (busy) return;
    setLoading(true);
    try {
      const history = await api<Message[]>(`/conversations/${id}/messages`);
      setConversationId(id);
      setMessages(history);
      setTraces([]);
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setBusy(true);
    setTraces([]);
    setStatus("正在建立排查任务");
    let id = conversationId;
    try {
      if (!id) {
        const conversation = await api<Conversation>("/conversations", {
          method: "POST",
          body: JSON.stringify({}),
        });
        id = conversation.id;
        setConversationId(id);
      }
      setMessages((items) => [
        ...items,
        { id: crypto.randomUUID(), role: "user", content: text },
      ]);
      await streamChat(id, text, crypto.randomUUID(), (name, payload) => {
        const data = payload as Record<string, unknown>;
        if (name === "status") setStatus(String(data.label));
        if (name === "tool")
          setTraces((items) => [...items, data as unknown as Trace]);
        if (name === "result") {
          setMessages((items) => [
            ...items,
            {
              id: String(data.message_id),
              role: "assistant",
              content: String(data.answer),
              metadata: {
                sources: data.sources as Source[],
                traces: data.traces as Trace[],
                draft: data.draft as Draft | null,
                mode: String(data.mode),
                duration_ms: Number(data.duration_ms),
              },
            },
          ]);
        }
        if (name === "error") notify(String(data.message));
      });
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setBusy(false);
      setRevision((v) => v + 1);
      onChanged();
    }
  }
  async function confirm(draft: Draft) {
    setConfirming(draft.id);
    try {
      const ticket = await api<Ticket>(`/drafts/${draft.id}/confirm`, {
        method: "POST",
        body: JSON.stringify({ idempotency_key: "draft-" + draft.id }),
      });
      notify("工单已创建，可以继续在工单中心跟进");
      setMessages((items) =>
        items.map((message) =>
          message.metadata?.draft?.id === draft.id
            ? {
                ...message,
                metadata: {
                  ...message.metadata,
                  draft: { ...draft, status: "confirmed" },
                },
              }
            : message,
        ),
      );
      onChanged();
      onTicket(ticket.id);
    } catch (reason) {
      notify((reason as Error).message);
    } finally {
      setConfirming("");
    }
  }
  return (
    <div className={"assistant-layout " + (!sideOpen ? "hide-context" : "")}>
      <aside className="conversation-rail">
        <button
          className="button secondary new-chat"
          disabled={busy}
          onClick={() => {
            setConversationId("");
            setMessages([]);
            setTraces([]);
          }}
        >
          <Plus size={16} />
          新的技术咨询
        </button>
        <span className="rail-label">最近的咨询</span>
        <div className="conversation-list">
          {conversations?.map((conversation) => (
            <button
              key={conversation.id}
              className={conversationId === conversation.id ? "active" : ""}
              disabled={busy}
              onClick={() => void selectConversation(conversation.id)}
            >
              <MessageSquare size={15} />
              <span>{conversation.title}</span>
            </button>
          ))}
        </div>
        <div className="rail-footer">
          <ShieldCheck size={17} />
          <p>
            每段会话独立保存，
            <br />
            支持随时回来继续排查。
          </p>
        </div>
      </aside>
      <section className="chat-panel">
        <div className="chat-heading">
          <div>
            <span className="assistant-emblem">
              <Sparkles size={18} />
            </span>
            <div>
              <h2>AI 支持助手</h2>
              <span>
                <i className="status-dot" />
                知识检索 · 日志分析 · 工单升级
              </span>
            </div>
          </div>
          <button
            className="icon-button"
            aria-label="切换知识面板"
            onClick={() => setSideOpen((open) => !open)}
          >
            <PanelRightClose size={19} />
          </button>
        </div>
        <div className="chat-scroll">
          {loading ? (
            <Loading />
          ) : !messages.length ? (
            <div className="chat-welcome">
              <span className="welcome-symbol">
                <WandSparkles size={34} />
              </span>
              <span className="eyebrow">LET'S FIND THE NEXT STEP</span>
              <h1>
                有什么技术问题，
                <br />
                我们一起排查。
              </h1>
              <p>
                描述现象，贴上脱敏日志。
                <br />
                我会查找依据、整理步骤，帮助你推进问题。
              </p>
              <div className="prompt-grid">
                {[
                  {
                    icon: Zap,
                    title: "服务突然不可用",
                    text: "FastAPI 部署后返回 502，日志里有 Connection refused，应该怎么排查？",
                  },
                  {
                    icon: Layers3,
                    title: "数据库连接异常",
                    text: "PostgreSQL 出现 QueuePool limit reached，怎么定位连接池耗尽的问题？",
                  },
                  {
                    icon: TicketIcon,
                    title: "整理问题并升级",
                    text: "Docker 应用无法通过 localhost 连接数据库，请帮我排查并生成工单。",
                  },
                ].map(({ icon: Icon, title, text }) => (
                  <button key={title} onClick={() => setInput(text)}>
                    <Icon size={18} />
                    <b>{title}</b>
                    <ArrowUpRight size={15} />
                    <span>{text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <article className={"message " + message.role} key={message.id}>
                  <span className={"message-avatar " + message.role}>
                    {message.role === "assistant" ? (
                      <Sparkles size={17} />
                    ) : (
                      <span>我</span>
                    )}
                  </span>
                  <div className="message-body">
                    <div className="message-author">
                      {message.role === "assistant" ? "SupportFlow" : "你"}
                      {message.role === "assistant" && (
                        <span className="tiny-pill">AI 助手</span>
                      )}
                    </div>
                    <div className="markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                    {message.metadata?.sources &&
                      message.metadata.sources.length > 0 && (
                        <div className="citation-chips">
                          {message.metadata.sources
                            .slice(0, 3)
                            .map((source) => (
                              <button
                                key={source.chunk_id}
                                onClick={() =>
                                  setSourceOpen(source.document_id)
                                }
                              >
                                <BookOpen size={12} />[{source.citation}]{" "}
                                {source.title}
                              </button>
                            ))}
                        </div>
                      )}
                    {message.metadata?.draft &&
                      (message.metadata.draft.status === "confirmed" ? (
                        <div className="confirmed-note">
                          <CheckCircle2 size={17} />
                          这份草稿已确认，可在工单中心继续跟进。
                        </div>
                      ) : (
                        <DraftPreview
                          draft={message.metadata.draft}
                          onConfirm={() =>
                            void confirm(message.metadata!.draft!)
                          }
                          busy={confirming === message.metadata.draft.id}
                        />
                      ))}
                    {message.metadata?.duration_ms !== undefined && (
                      <div className="message-foot">
                        {message.metadata.mode === "demo"
                          ? "离线演示"
                          : "模型辅助"}{" "}
                        · {(message.metadata.duration_ms / 1000).toFixed(1)}s
                      </div>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          {busy && (
            <div className="thinking">
              <LoaderCircle className="spin" size={17} />
              <span>{status}</span>
              {traces.length > 0 && (
                <small>已完成 {traces.length} 个工具步骤</small>
              )}
            </div>
          )}
          <div ref={endRef} />
        </div>
        <div className="composer-wrap">
          <form className="composer" onSubmit={send}>
            <textarea
              aria-label="描述技术问题"
              placeholder="描述你遇到的问题，或粘贴一段脱敏日志…"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              maxLength={12000}
              rows={3}
              disabled={busy}
            />
            <div>
              <span>
                <ShieldCheck size={13} />
                敏感凭据请先脱敏
              </span>
              <button
                className="send-button"
                aria-label="发送问题"
                disabled={busy || !input.trim()}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <ArrowUpRight size={21} />
                )}
              </button>
            </div>
          </form>
          <p className="composer-note">
            AI 可能出错，请核实排查建议。正式工单需经你确认。{" "}
            <span>Enter 发送 · Shift + Enter 换行</span>
          </p>
        </div>
      </section>
      {sideOpen && (
        <aside className="context-panel">
          <div className="context-title">
            <BookOpen size={17} />
            <h3>排查上下文</h3>
          </div>
          <div className="context-section">
            <span className="rail-label">
              引用的知识 <b>{sources.length.toString().padStart(2, "0")}</b>
            </span>
            {sources.length ? (
              sources.map((source) => (
                <button
                  className="source-card"
                  key={source.chunk_id}
                  onClick={() => setSourceOpen(source.document_id)}
                >
                  <span className="source-index">{source.citation}</span>
                  <div>
                    <b>{source.title}</b>
                    <p>{source.heading}</p>
                    <span>
                      {source.product} · {source.version}
                    </span>
                  </div>
                  <ArrowUpRight size={13} />
                </button>
              ))
            ) : (
              <div className="context-empty">
                <FileText size={24} />
                <p>
                  分析开始后，
                  <br />
                  引用的知识会显示在这里。
                </p>
              </div>
            )}
          </div>
          <div className="context-section">
            <span className="rail-label">
              工具执行记录 <b>{tools.length.toString().padStart(2, "0")}</b>
            </span>
            {tools.length ? (
              <div className="tool-list">
                {tools.map((trace, index) => (
                  <div key={index}>
                    {trace.status === "failed" ? (
                      <X size={15} />
                    ) : (
                      <CheckCircle2 size={15} />
                    )}
                    <span>
                      {TOOLS[trace.name] || trace.name}
                      <small>
                        {trace.status === "failed" ? "未完成 · " : ""}
                        {trace.duration_ms} ms
                      </small>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="context-hint">
                工具调用过程可追溯，
                <br />
                每一步都有记录。
              </p>
            )}
          </div>
          <div className="context-tip">
            <ShieldCheck size={19} />
            <h4>你始终掌握决定权</h4>
            <p>
              助手提供排查建议与工单草稿；创建工单由你确认，状态由支持团队跟进。
            </p>
          </div>
        </aside>
      )}
      {sourceOpen && (
        <DocumentModal id={sourceOpen} onClose={() => setSourceOpen("")} />
      )}
    </div>
  );
}

function RunsPage({ revision }: { revision: number }) {
  const { data, error } = useLoad<Run[]>("/runs", revision);
  return (
    <div className="page">
      <div className="page-title">
        <div>
          <span className="eyebrow">OBSERVE & IMPROVE</span>
          <h1>每一次运行，都有迹可循。</h1>
          <p>查看当前账号最近 50 次任务的结果、工具调用与模型用量。</p>
        </div>
        <span className="date-chip">
          <Activity size={15} />
          实际运行数据
        </span>
      </div>
      <ErrorBox message={error} />
      <div className="panel">
        {!data ? (
          <Loading />
        ) : !data.length ? (
          <Empty
            title="还没有运行记录"
            description="向 AI 支持助手提问后，会在这里记录执行结果。"
            icon={Activity}
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>运行 ID / 时间</th>
                  <th>模式</th>
                  <th>结果</th>
                  <th>耗时</th>
                  <th>工具调用</th>
                  <th>输入 / 输出 Token</th>
                </tr>
              </thead>
              <tbody>
                {data.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <span className="mono">{run.id.slice(0, 8)}</span>
                      <span className="ticket-sub">
                        {date(run.created_at, true)}
                      </span>
                      {run.error && (
                        <span className="run-error">{run.error}</span>
                      )}
                    </td>
                    <td>
                      <span className="tiny-pill">
                        {run.mode === "demo" ? "离线演示" : "真实模型"}
                      </span>
                    </td>
                    <td>
                      <span className={"run-status " + run.status}>
                        {run.status === "completed"
                          ? "已完成"
                          : run.status === "running"
                            ? "运行中"
                            : "未完成"}
                      </span>
                    </td>
                    <td>{(run.duration_ms / 1000).toFixed(2)}s</td>
                    <td>{run.tool_count}</td>
                    <td className="mono">
                      {run.input_tokens.toLocaleString()} /{" "}
                      {run.output_tokens.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <p className="page-note">
        离线演示不消耗模型
        Token。耗时为端到端执行时间；工具完成不代表问题根因已经验证。
      </p>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null),
    [initializing, setInitializing] = useState(true),
    [page, setPage] = useState<Page>("dashboard"),
    [revision, setRevision] = useState(0),
    [toast, setToast] = useState(""),
    [newTicket, setNewTicket] = useState(false),
    [ticketId, setTicketId] = useState(""),
    [prompt, setPrompt] = useState("");
  const { data: health } = useLoad<{
    agent_mode: string;
    demo_enabled: boolean;
  }>("/health");
  useEffect(() => {
    if (!sessionStorage.getItem("supportflow-token")) {
      setInitializing(false);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setToken(""))
      .finally(() => setInitializing(false));
  }, []);
  useEffect(() => {
    const expired = () => {
      setToken("");
      setUser(null);
    };
    window.addEventListener("supportflow-expired", expired);
    return () => window.removeEventListener("supportflow-expired", expired);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 4500);
    return () => clearTimeout(timer);
  }, [toast]);
  const notify: Notify = (message) => setToast(message);
  function navigate(next: Page, text = "") {
    setPage(next);
    setPrompt(text);
  }
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setToken("");
      setUser(null);
      setPage("dashboard");
    }
  }
  const changed = () => setRevision((v) => v + 1);
  if (initializing)
    return (
      <div className="app-loading">
        <Mark />
        <Loading />
      </div>
    );
  if (!user) return <Login onLogin={setUser} />;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => navigate("dashboard")}>
          <Mark />
          <span>
            SupportFlow<span className="brand-sub">技术支持协作平台</span>
          </span>
        </button>
        <div className="workspace-switch">
          <span className="workspace-avatar">S</span>
          <div>
            <b>技术支持工作区</b>
            <small>Team workspace</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="nav-label">工作空间</span>
        <nav>
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "assistant" && <span className="ai-label">AI</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-help">
          <span className="help-icon">
            <Zap size={17} />
          </span>
          <h4>从提问到解决</h4>
          <p>
            用知识辅助排障，
            <br />
            用工单连接团队。
          </p>
          <button onClick={() => navigate("assistant")}>
            开始一次咨询
            <ArrowUpRight size={14} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">{user.name.slice(-2)}</span>
          <div>
            <b>{user.name}</b>
            <small>
              {user.role === "engineer"
                ? "支持工程师"
                : user.role === "admin"
                  ? "管理员"
                  : "提问用户"}
            </small>
          </div>
          <button
            className="icon-button"
            aria-label="退出登录"
            title="退出登录"
            onClick={() => void logout()}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <span>工作空间</span>
            <ChevronRight size={14} />
            <b>{NAV.find((item) => item.id === page)?.label}</b>
          </div>
          <div className="topbar-actions">
            <span className="mode-chip">
              <i />
              {health?.agent_mode === "live" ? "模型模式" : "离线演示"}
            </span>
            <span className="header-divider" />
            <button
              className="button secondary small"
              onClick={() => setNewTicket(true)}
            >
              <Plus size={15} />
              新建工单
            </button>
          </div>
        </header>
        <main
          className={
            page === "assistant"
              ? "main-content assistant-main"
              : "main-content"
          }
        >
          {page === "dashboard" && (
            <DashboardPage
              user={user}
              revision={revision}
              navigate={navigate}
              onTicket={setTicketId}
            />
          )}{" "}
          {page === "assistant" && (
            <AssistantPage
              initialPrompt={prompt}
              clearPrompt={() => setPrompt("")}
              notify={notify}
              onTicket={setTicketId}
              onChanged={changed}
            />
          )}{" "}
          {page === "tickets" && (
            <TicketsPage
              revision={revision}
              onTicket={setTicketId}
              onNew={() => setNewTicket(true)}
              notify={notify}
            />
          )}{" "}
          {page === "knowledge" && (
            <KnowledgePage user={user} notify={notify} />
          )}{" "}
          {page === "runs" && <RunsPage revision={revision} />}
        </main>
      </div>
      {newTicket && (
        <NewTicketModal
          onClose={() => setNewTicket(false)}
          onCreated={(id) => {
            setNewTicket(false);
            setTicketId(id);
            changed();
          }}
          notify={notify}
        />
      )}{" "}
      {ticketId && (
        <TicketDetail
          id={ticketId}
          user={user}
          onClose={() => setTicketId("")}
          onChanged={changed}
          notify={notify}
        />
      )}{" "}
      {toast && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          <span>{toast}</span>
          <button aria-label="关闭提示" onClick={() => setToast("")}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
