import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import App from "./App";
import { api, setToken, streamChat } from "./api";

vi.mock("./api", () => ({
  api: vi.fn(),
  setToken: vi.fn(),
  streamChat: vi.fn(),
}));
const user = {
  id: "user1",
  name: "林知远",
  email: "engineer@supportflow.local",
  role: "engineer",
};
const ticket = {
  id: "ticket1",
  number: "SF-TEST-001",
  title: "测试 502 故障",
  description: "这是需要跟进的技术问题。",
  owner_name: "陈同学",
  owner_id: "user1",
  assignee_name: null,
  assignee_id: null,
  priority: "high",
  category: "部署与运行",
  status: "open",
  version: 1,
  created_at: "2026-10-26T01:00:00Z",
  updated_at: "2026-10-26T01:00:00Z",
  comments: [],
  events: [],
};
const draft = {
  id: "draft1",
  title: "测试 502 故障",
  description: "这是待用户确认的技术支持草稿。",
  priority: "high",
  category: "部署与运行",
  status: "pending",
  conversation_id: "conversation1",
  created_at: "2026-10-26T01:00:00Z",
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/health")
      return { demo_enabled: true, agent_mode: "demo" } as never;
    if (path === "/auth/login")
      return { access_token: "test-token", user } as never;
    if (path === "/dashboard")
      return {
        total: 1,
        counts: { open: 1, in_progress: 0, waiting: 0, resolved: 0, closed: 0 },
        urgent: 1,
        knowledge_count: 5,
        recent_tickets: [ticket],
        agent: {
          mode: "demo",
          runs: 0,
          success_rate: null,
          avg_duration_ms: 0,
          tool_calls: 0,
        },
      } as never;
    if (path === "/conversations")
      return { id: "conversation1", title: "新的技术咨询" } as never;
    if (path === "/drafts/draft1/confirm") return ticket as never;
    if (path === "/tickets/ticket1") return ticket as never;
    if (path === "/users") return [user] as never;
    if (path.startsWith("/tickets?"))
      return { items: [ticket], total: 1, page_size: 20 } as never;
    if (path === "/drafts") return [] as never;
    return [] as never;
  });
});

async function login() {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /进入工作台/ }));
  await screen.findByText(/林知远，工作顺利/);
}

describe("SupportFlow main workflows", () => {
  it("logs in and renders actual ticket data", async () => {
    await login();
    expect(setToken).toHaveBeenCalledWith("test-token");
    expect(screen.getByText("测试 502 故障")).toBeTruthy();
  });
  it("keeps agent-generated drafts pending until the user confirms", async () => {
    vi.mocked(api).mockImplementationOnce(
      async () => ({ demo_enabled: true, agent_mode: "demo" }) as never,
    );
    await login();
    vi.mocked(api).mockImplementation(async (path, options) => {
      if (path === "/conversations")
        return (
          options?.method === "POST"
            ? { id: "conversation1", title: "新的技术咨询" }
            : []
        ) as never;
      if (path === "/drafts/draft1/confirm") return ticket as never;
      if (path === "/tickets/ticket1") return ticket as never;
      if (path === "/users") return [user] as never;
      return [] as never;
    });
    vi.mocked(streamChat).mockImplementation(
      async (_id, _text, _request, callback) => {
        callback("tool", {
          name: "search_knowledge",
          duration_ms: 1,
          status: "completed",
          input: {},
        });
        callback("result", {
          message_id: "message1",
          answer: "已生成草稿，等待你的确认。",
          sources: [],
          traces: [],
          draft,
          mode: "demo",
          duration_ms: 5,
        });
        callback("done", { run_id: "run1" });
      },
    );
    fireEvent.click(screen.getByRole("button", { name: /AI 支持助手/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "描述技术问题" }), {
      target: { value: "FastAPI 502，请生成工单" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    const confirm = await screen.findByRole("button", { name: /确认创建工单/ });
    expect(
      vi.mocked(api).mock.calls.some(([path]) => path.includes("/confirm")),
    ).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(
        vi
          .mocked(api)
          .mock.calls.some(([path]) => path === "/drafts/draft1/confirm"),
      ).toBe(true),
    );
    expect(await screen.findByText("SF-TEST-001")).toBeTruthy();
  });
  it("uses status filters when browsing tickets", async () => {
    await login();
    fireEvent.click(screen.getByRole("button", { name: "工单中心" }));
    fireEvent.click(await screen.findByRole("button", { name: "处理中" }));
    await waitFor(() =>
      expect(
        vi
          .mocked(api)
          .mock.calls.some(([path]) => path.includes("status=in_progress")),
      ).toBe(true),
    );
  });
});
