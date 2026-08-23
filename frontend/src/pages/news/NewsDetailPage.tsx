import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../../shared/api";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { RichTextRenderer } from "../../shared/ui/RichTextRenderer";

export function NewsDetailPage() {
  const { publicationId = "" } = useParams();
  const publication = useQuery({
    queryKey: ["publication", publicationId],
    queryFn: () => api.publication(publicationId),
  });
  if (publication.isPending) return <PageState kind="loading" />;
  if (publication.isError) return <PageState error={publication.error} />;
  const item = publication.data;
  return (
    <article className="page-stack publication-detail">
      <Link className="back-link" to="/news">
        ← Все новости
      </Link>
      <header>
        <Badge>{item.category.name}</Badge>
        <h1>{item.title}</h1>
        <p className="page-description">{item.summary}</p>
        <p className="publication-meta">
          {item.author.full_name} ·{" "}
          {new Date(item.published_at).toLocaleDateString("ru-RU")} ·{" "}
          {item.view_count} просмотров
        </p>
      </header>
      <Card>
        <RichTextRenderer document={item.body} />
      </Card>
    </article>
  );
}
