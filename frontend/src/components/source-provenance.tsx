import { ExternalLink, BookOpenCheck } from "lucide-react";
import { externalSourceUrl } from "../lib/utils";
import { Badge } from "./ui/badge";

type Provenance = {
  source: string;
  source_url?: string | null;
  source_license?: string | null;
  retrieved_at?: string | null;
};

export function SourceProvenance({
  source,
  compact = false,
}: {
  source: Provenance;
  compact?: boolean;
}) {
  const url = externalSourceUrl(source.source_url);
  const retrieval = source.retrieved_at ? new Date(source.retrieved_at) : null;
  const retrieved =
    retrieval && !Number.isNaN(retrieval.getTime())
      ? new Intl.DateTimeFormat("zh-CN", {
          timeZone: "Asia/Shanghai",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
        }).format(retrieval)
      : null;
  if (!url && !source.source_license && !retrieved) return null;
  return (
    <div className={"source-provenance " + (compact ? "compact" : "")}>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer">
          <ExternalLink size={12} />
          <span>查看来源原文</span>
        </a>
      )}
      {source.source_license && (
        <Badge variant="outline" className="source-license">
          <BookOpenCheck size={11} />
          {source.source_license}
        </Badge>
      )}
      {!compact && retrieved && <span>采集于 {retrieved}</span>}
    </div>
  );
}
