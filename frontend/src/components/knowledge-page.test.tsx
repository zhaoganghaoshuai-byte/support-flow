import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { api } from "../api";
import { KnowledgePage } from "./knowledge-page";
import { SourceProvenance } from "./source-provenance";

vi.mock("../api", () => ({ api: vi.fn() }));
const user = {
  id: "engineer",
  name: "工程师",
  email: "engineer@example.test",
  role: "engineer" as const,
};
const documents = [
  {
    id: "fastapi-v1",
    title: "FastAPI 部署文档",
    product: "FastAPI",
    version: "0.110",
    source: "FastAPI documentation",
    source_url: "https://fastapi.tiangolo.com/deployment/",
    source_license: "MIT",
    retrieved_at: "2026-10-27T00:00:00Z",
    characters: 1000,
    created_at: "2026-10-27T00:00:00Z",
  },
  {
    id: "fastapi-common",
    title: "FastAPI 通用排查",
    product: "FastAPI",
    version: "通用",
    source: "团队资料",
    characters: 100,
    created_at: "2026-10-27T00:00:00Z",
  },
  {
    id: "docker",
    title: "Docker 网络排查",
    product: "Docker",
    version: "27",
    source: "团队资料",
    characters: 100,
    created_at: "2026-10-27T00:00:00Z",
  },
];

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/health") return { retrieval_mode: "bm25" } as never;
    if (path === "/knowledge") return documents as never;
    if (path.startsWith("/knowledge/search?"))
      return {
        items: [
          {
            ...documents[0],
            document_id: "fastapi-v1",
            chunk_id: "one",
            heading: "部署",
            content: "检查应用进程和监听地址。",
            score: 2.5,
          },
        ],
      } as never;
    if (path === "/knowledge/fastapi-v1")
      return {
        ...documents[0],
        content: "## 部署步骤\n检查应用进程和监听地址。",
      } as never;
    return {} as never;
  });
});

describe("knowledge workspace", () => {
  it("sends product and version scope to the search API", async () => {
    render(<KnowledgePage user={user} notify={vi.fn()} />);
    await screen.findByText("FastAPI 部署文档");
    fireEvent.change(screen.getByRole("combobox", { name: "产品筛选" }), {
      target: { value: "FastAPI" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "版本筛选" }), {
      target: { value: "0.110" },
    });
    expect(screen.queryByText("Docker 网络排查")).toBeNull();
    expect(screen.getByText("FastAPI 通用排查")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "检索知识库" }), {
      target: { value: "502 Connection refused" },
    });
    fireEvent.click(screen.getByRole("button", { name: "检索知识" }));
    await waitFor(() =>
      expect(
        vi.mocked(api).mock.calls.some(([path]) => {
          if (!path.startsWith("/knowledge/search?")) return false;
          const parameters = new URLSearchParams(path.split("?")[1]);
          return (
            parameters.get("q") === "502 Connection refused" &&
            parameters.get("product") === "FastAPI" &&
            parameters.get("version") === "0.110"
          );
        }),
      ).toBe(true),
    );
    expect(await screen.findByText("检查应用进程和监听地址。")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "查看来源原文" }).getAttribute("href"),
    ).toBe("https://fastapi.tiangolo.com/deployment/");
  });

  it("opens a labeled accessible dialog and closes it with Escape", async () => {
    render(<KnowledgePage user={user} notify={vi.fn()} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /FastAPI 部署文档/ }),
    );
    expect(
      await screen.findByRole("dialog", { name: "FastAPI 部署文档" }),
    ).toBeTruthy();
    expect(screen.getByText("检查应用进程和监听地址。")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("ignores an old search after changing filters while a newer search is pending", async () => {
    let resolveOld!: (value: unknown) => void;
    let resolveCurrent!: (value: unknown) => void;
    const oldResponse = new Promise<unknown>((resolve) => {
      resolveOld = resolve;
    });
    const currentResponse = new Promise<unknown>((resolve) => {
      resolveCurrent = resolve;
    });
    const previous = vi.mocked(api).getMockImplementation()!;
    vi.mocked(api).mockImplementation(async (path, options) => {
      if (path.startsWith("/knowledge/search?")) {
        const product = new URLSearchParams(path.split("?")[1]).get("product");
        return (await (product === "FastAPI"
          ? oldResponse
          : currentResponse)) as never;
      }
      return previous(path, options);
    });
    render(<KnowledgePage user={user} notify={vi.fn()} />);
    await screen.findByText("FastAPI 部署文档");
    const filter = screen.getByRole("combobox", { name: "产品筛选" });
    const searchButton = screen.getByRole("button", { name: "检索知识" });
    fireEvent.change(filter, { target: { value: "FastAPI" } });
    fireEvent.change(screen.getByRole("textbox", { name: "检索知识库" }), {
      target: { value: "部署排查" },
    });
    fireEvent.click(searchButton);
    expect((searchButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(filter, { target: { value: "Docker" } });
    expect((searchButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(searchButton);

    await act(async () => {
      resolveOld({
        items: [
          {
            ...documents[0],
            document_id: "fastapi-v1",
            chunk_id: "old-result",
            heading: "旧筛选结果",
            content: "不应出现的 FastAPI 旧搜索内容",
            score: 2,
          },
        ],
      });
    });
    expect(screen.queryByText("不应出现的 FastAPI 旧搜索内容")).toBeNull();
    expect(screen.queryByText("FastAPI 部署文档")).toBeNull();
    expect(screen.getByText("Docker 网络排查")).toBeTruthy();
    expect((searchButton as HTMLButtonElement).disabled).toBe(true);

    await act(async () => {
      resolveCurrent({
        items: [
          {
            ...documents[2],
            document_id: "docker",
            chunk_id: "current-result",
            heading: "当前筛选结果",
            content: "仅展示 Docker 当前筛选的搜索内容",
            score: 3,
          },
        ],
      });
    });
    expect(screen.getByText("仅展示 Docker 当前筛选的搜索内容")).toBeTruthy();
    expect(screen.queryByText("不应出现的 FastAPI 旧搜索内容")).toBeNull();
    expect((searchButton as HTMLButtonElement).disabled).toBe(false);
  });

  it("keeps an import error visible inside the document form", async () => {
    const previous = vi.mocked(api).getMockImplementation()!;
    vi.mocked(api).mockImplementation(async (path, options) => {
      if (path === "/knowledge" && options?.method === "POST")
        throw new Error("来源网址不可用，请检查后重试");
      return previous(path, options);
    });
    render(<KnowledgePage user={user} notify={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "添加知识" }));
    const form = within(screen.getByRole("dialog", { name: "添加团队知识" }));
    fireEvent.change(form.getByLabelText("文档标题"), {
      target: { value: "项目部署说明" },
    });
    fireEvent.change(form.getByRole("textbox", { name: "产品" }), {
      target: { value: "FastAPI" },
    });
    fireEvent.change(form.getByLabelText("正文（Markdown 或纯文本）"), {
      target: {
        value:
          "这是一份足够长的项目部署说明文档，用于验证入库错误后表单仍保留内容。",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并加入检索" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "来源网址不可用，请检查后重试",
    );
    expect(screen.getByRole("dialog", { name: "添加团队知识" })).toBeTruthy();
    expect((screen.getByLabelText("文档标题") as HTMLInputElement).value).toBe(
      "项目部署说明",
    );
  });

  it("does not render unsafe or credential-bearing provenance links", () => {
    const { rerender } = render(
      <SourceProvenance
        source={{ source: "untrusted", source_url: "javascript:alert(1)" }}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    rerender(
      <SourceProvenance
        source={{
          source: "untrusted",
          source_url: "https://user:secret@example.test/",
        }}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});
