import { LoaderCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useResource } from "../hooks/use-resource";
import type { Document } from "../types";
import { AppDialog } from "./app-dialog";
import { SourceProvenance } from "./source-provenance";

export function DocumentDialog({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const { data, error, loading } = useResource<Document>(
    "/knowledge/" + encodeURIComponent(id),
  );
  return (
    <AppDialog wide title={data?.title || "知识文档"} onClose={onClose}>
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      {loading && !data ? (
        <div className="loading" role="status">
          <LoaderCircle className="spin" size={22} />
          <span>正在加载文档…</span>
        </div>
      ) : (
        data && (
          <>
            <div className="document-meta">
              <span className="product-tag">{data.product}</span>
              <span>{data.version}</span>
              <span>{data.source}</span>
            </div>
            <SourceProvenance source={data} />
            <div className="markdown document-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {data.content || ""}
              </ReactMarkdown>
            </div>
          </>
        )
      )}
    </AppDialog>
  );
}
