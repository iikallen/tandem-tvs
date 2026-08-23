import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../shared/api";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { t } from "../../shared/i18n";
import { EditorialGuard } from "./EditorialGuard";

export function EditorialListPage() {
  return (
    <EditorialGuard>
      <EditorialList />
    </EditorialGuard>
  );
}

function EditorialList() {
  const publications = useQuery({
    queryKey: ["editorial"],
    queryFn: api.editorial,
  });
  if (publications.isPending) return <PageState kind="loading" />;
  if (publications.isError) return <PageState error={publications.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{t("publications")}</h1>
          <p className="page-description">{t("publicationsDescription")}</p>
        </div>
        <Link className="button" to="/editorial/publications/new">
          {t("newPublication")}
        </Link>
      </header>
      {publications.data.results.length === 0 ? (
        <div className="state">
          <div className="state__content">
            <h2>{t("noDrafts")}</h2>
          </div>
        </div>
      ) : (
        <div className="editorial-list">
          {publications.data.results.map((publication) => (
            <Link
              key={publication.id}
              to={`/editorial/publications/${publication.id}`}
            >
              <Card className="editorial-card">
                <div>
                  <Badge
                    tone={
                      publication.status === "PUBLISHED" ? "success" : undefined
                    }
                  >
                    {publication.status === "PUBLISHED"
                      ? t("published")
                      : t("draft")}
                  </Badge>
                </div>
                <h2>{publication.title}</h2>
                <p>{publication.summary}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
