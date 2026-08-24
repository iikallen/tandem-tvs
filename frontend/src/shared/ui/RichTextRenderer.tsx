import type { ReactNode } from "react";

import type { RichTextNode } from "../api";
import { t } from "../i18n";

function safeHref(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  return /^(https?:\/\/|mailto:|\/|#)/i.test(value) ? value : undefined;
}

function renderNode(node: RichTextNode, key: number): ReactNode {
  if (node.type === "text") {
    let content: ReactNode = node.text ?? "";
    for (const mark of [...(node.marks ?? [])].reverse()) {
      if (mark.type === "bold") content = <strong>{content}</strong>;
      if (mark.type === "italic") content = <em>{content}</em>;
      if (mark.type === "link") {
        const href = safeHref(mark.attrs?.href);
        if (href) content = <a href={href}>{content}</a>;
      }
    }
    return <span key={key}>{content}</span>;
  }
  if (node.type === "hardBreak") return <br key={key} />;
  const children = node.content?.map(renderNode) ?? null;
  if (node.type === "paragraph") return <p key={key}>{children}</p>;
  if (node.type === "heading" && node.attrs?.level === 2)
    return <h2 key={key}>{children}</h2>;
  if (node.type === "heading" && node.attrs?.level === 3)
    return <h3 key={key}>{children}</h3>;
  if (node.type === "bulletList") return <ul key={key}>{children}</ul>;
  if (node.type === "orderedList") return <ol key={key}>{children}</ol>;
  if (node.type === "listItem") return <li key={key}>{children}</li>;
  if (node.type === "blockquote")
    return <blockquote key={key}>{children}</blockquote>;
  if (node.type === "table")
    return (
      <table key={key}>
        <tbody>{children}</tbody>
      </table>
    );
  if (node.type === "tableRow") return <tr key={key}>{children}</tr>;
  if (node.type === "tableCell") return <td key={key}>{children}</td>;
  if (node.type === "tableHeader") return <th key={key}>{children}</th>;
  const assetId =
    typeof node.attrs?.asset_id === "string" ? node.attrs.asset_id : undefined;
  if (node.type === "assetImage" && assetId)
    return <img key={key} src={`/api/v1/media/${assetId}/content`} alt="" />;
  if (node.type === "internalVideo" && assetId)
    return (
      <video
        key={key}
        controls
        preload="metadata"
        src={`/api/v1/media/${assetId}/content`}
      />
    );
  if (node.type === "attachment" && assetId)
    return (
      <a
        key={key}
        className="attachment-link"
        href={`/api/v1/media/${assetId}/content`}
      >
        {t("downloadAttachment")}
      </a>
    );
  if (node.type === "doc") return children;
  return null;
}

export function RichTextRenderer({ document }: { document: RichTextNode }) {
  return <div className="rich-text">{renderNode(document, 0)}</div>;
}
