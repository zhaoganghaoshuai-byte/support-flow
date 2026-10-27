import { useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowUpRight,
  BookOpen,
  FileText,
  LoaderCircle,
  Plus,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { api } from "../api";
import { useResource } from "../hooks/use-resource";
import type { Document, KnowledgeSearchSource, User } from "../types";
import { AppDialog } from "./app-dialog";
import { DocumentDialog } from "./document-dialog";
import { SourceProvenance } from "./source-provenance";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";

function shortDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

export function KnowledgePage({
  user,
  notify,
}: {
  user: User;
  notify: (message: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [product, setProduct] = useState("");
  const [version, setVersion] = useState("");
  const [results, setResults] = useState<KnowledgeSearchSource[] | null>(null);
  const searchGeneration = useRef(0);
  const [opened, setOpened] = useState("");
  const [adding, setAdding] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [content, setContent] = useState("");
  const [searchError, setSearchError] = useState("");
  const [formError, setFormError] = useState("");
  const {
    data: documents,
    error,
    loading,
  } = useResource<Document[]>("/knowledge", revision);
  const { data: health } = useResource<{ retrieval_mode?: string }>("/health");
  const products = useMemo(
    () =>
      [
        ...new Set((documents || []).map((document) => document.product)),
      ].sort(),
    [documents],
  );
  const versions = useMemo(
    () =>
      [
        ...new Set(
          (documents || [])
            .filter((document) => !product || document.product === product)
            .map((document) => document.version),
        ),
      ].sort(),
    [documents, product],
  );
  const visible = (documents || []).filter(
    (document) =>
      (!product || document.product === product) &&
      (!version || document.version === version || document.version === "通用"),
  );
  const methodLabel =
    health?.retrieval_mode === "hybrid"
      ? "关键词与语义混合检索"
      : health?.retrieval_mode === "vector"
        ? "语义检索"
        : "BM25 关键词检索";

  function invalidateResults() {
    searchGeneration.current += 1;
    setResults(null);
    setSearchError("");
    setSearching(false);
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) {
      invalidateResults();
      return;
    }
    const generation = ++searchGeneration.current;
    setSearching(true);
    setSearchError("");
    const parameters = new URLSearchParams({ q: query.trim() });
    if (product) parameters.set("product", product);
    if (version) parameters.set("version", version);
    try {
      const response = await api<{ items: KnowledgeSearchSource[] }>(
        "/knowledge/search?" + parameters,
      );
      if (generation === searchGeneration.current) setResults(response.items);
    } catch (reason) {
      if (generation === searchGeneration.current)
        setSearchError((reason as Error).message);
    } finally {
      if (generation === searchGeneration.current) setSearching(false);
    }
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const form = new FormData(event.currentTarget);
    try {
      const payload = Object.fromEntries(form);
      if (!payload.source_url) delete payload.source_url;
      await api("/knowledge", {
        method: "POST",
        body: JSON.stringify({ ...payload, content }),
      });
      setAdding(false);
      setContent("");
      setRevision((value) => value + 1);
      invalidateResults();
      notify("文档已入库，可立即检索");
    } catch (reason) {
      setFormError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page knowledge-page">
      <div className="page-title">
        <div>
          <span className="eyebrow">TEAM KNOWLEDGE</span>
          <h1>让经验，成为下一次的答案。</h1>
          <p>维护团队运维知识，为 AI 回答提供可追溯的依据。</p>
        </div>
        {user.role !== "requester" && (
          <Button
            onClick={() => {
              setFormError("");
              setAdding(true);
            }}
          >
            <Plus size={17} />
            添加知识
          </Button>
        )}
      </div>
      <Card className="knowledge-search">
        <div className="knowledge-search-icon">
          <BookOpen size={22} />
        </div>
        <form onSubmit={search}>
          <Input
            aria-label="检索知识库"
            placeholder="描述问题，检索相关的排查经验…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!event.target.value) invalidateResults();
            }}
          />
          <Button disabled={searching} aria-busy={searching}>
            {searching ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Search size={16} />
            )}
            检索知识
          </Button>
        </form>
        <span>{methodLabel} · 支持中文与英文</span>
        <div className="knowledge-filters flex w-full flex-wrap items-end gap-3">
          <span className="filter-label">
            <SlidersHorizontal size={14} />
            检索范围
          </span>
          <label>
            产品
            <select
              aria-label="产品筛选"
              value={product}
              onChange={(event) => {
                setProduct(event.target.value);
                setVersion("");
                invalidateResults();
              }}
            >
              <option value="">全部产品</option>
              {products.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            版本
            <select
              aria-label="版本筛选"
              value={version}
              onChange={(event) => {
                setVersion(event.target.value);
                invalidateResults();
              }}
            >
              <option value="">全部版本</option>
              {versions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          {(product || version) && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setProduct("");
                setVersion("");
                invalidateResults();
              }}
            >
              清除筛选
            </Button>
          )}
        </div>
      </Card>
      {(error || searchError) && (
        <div className="error-box" role="alert">
          {searchError || error}
        </div>
      )}
      <div className="section-label">
        <h2>
          {results ? "检索结果" : "全部知识"}
          <Badge className="count">
            {results ? results.length : visible.length}
          </Badge>
        </h2>
        <span>
          {results
            ? "按相关度排序，来源可追溯"
            : "共享团队资料 · 支持产品与版本筛选"}
        </span>
      </div>
      {loading && !documents ? (
        <div className="loading" role="status">
          <LoaderCircle className="spin" size={22} />
          <span>正在加载知识库…</span>
        </div>
      ) : results ? (
        <div className="search-results" aria-live="polite">
          {results.length ? (
            results.map((item) => (
              <Card className="result-card" key={item.chunk_id}>
                <button
                  className="result-open"
                  onClick={() => setOpened(item.document_id)}
                >
                  <div>
                    <span className="product-tag">{item.product}</span>
                    <span className="muted">
                      相关度 {item.score.toFixed(2)}
                    </span>
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
                <SourceProvenance source={item} />
              </Card>
            ))
          ) : (
            <div className="empty">
              <span>
                <Search size={27} />
              </span>
              <h3>没有找到匹配内容</h3>
              <p>试试其他产品、版本、错误码或日志关键词。</p>
            </div>
          )}
        </div>
      ) : visible.length ? (
        <div className="knowledge-grid">
          {visible.map((document, index) => (
            <Card className="knowledge-document" key={document.id}>
              <button
                className="document-card"
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
                  <span>{shortDate(document.created_at)}</span>
                </div>
              </button>
              <SourceProvenance source={document} compact />
            </Card>
          ))}
        </div>
      ) : (
        !error && (
          <div className="empty">
            <span>
              <BookOpen size={27} />
            </span>
            <h3>当前范围还没有知识文档</h3>
            <p>调整筛选条件，或添加团队资料后再检索。</p>
          </div>
        )
      )}
      {opened && <DocumentDialog id={opened} onClose={() => setOpened("")} />}
      {adding && (
        <AppDialog
          title="添加团队知识"
          onClose={() => {
            if (!saving) setAdding(false);
          }}
        >
          <form className="stack-form" onSubmit={add}>
            {formError && (
              <div className="error-box" role="alert">
                {formError}
              </div>
            )}
            <label>
              文档标题
              <Input name="title" minLength={3} maxLength={200} required />
            </label>
            <div className="form-row">
              <label>
                产品
                <Input
                  name="product"
                  placeholder="例如 FastAPI"
                  required
                  maxLength={80}
                />
              </label>
              <label>
                版本
                <Input
                  name="version"
                  defaultValue="通用"
                  required
                  maxLength={40}
                />
              </label>
            </div>
            <label>
              来源说明
              <Input
                name="source"
                defaultValue="团队知识库"
                required
                maxLength={500}
              />
            </label>
            <label>
              来源网址（可选）
              <Input
                name="source_url"
                type="url"
                placeholder="https://官方文档地址"
                maxLength={1000}
              />
            </label>
            <label>
              正文（Markdown 或纯文本）
              <Textarea
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
              <Input
                type="file"
                accept=".md,.txt"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  if (file.size > 240000) {
                    setFormError("文件过大，请控制在 6 万字符内");
                    return;
                  }
                  const text = await file.text();
                  if (text.length > 60000) {
                    setFormError("正文超过 6 万字符，请拆分为多份文档");
                    return;
                  }
                  setContent(text);
                  setFormError("");
                }}
              />
            </label>
            <Button disabled={saving} aria-busy={saving}>
              {saving ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Plus size={16} />
              )}
              保存并加入检索
            </Button>
          </form>
        </AppDialog>
      )}
    </div>
  );
}
