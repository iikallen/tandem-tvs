import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../../shared/api";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

export function VersionHistoryPage() {
  return (
    <EditorialGuard>
      <VersionHistory />
    </EditorialGuard>
  );
}

function VersionHistory() {
  const { publicationId = "" } = useParams();
  const versions = useQuery({
    queryKey: ["versions", publicationId],
    queryFn: () => api.versions(publicationId),
  });
  if (versions.isPending) return <PageState kind="loading" />;
  if (versions.isError) return <PageState error={versions.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">Редакция</p>
          <h1>История версий</h1>
        </div>
      </header>
      <div className="version-list">
        {versions.data.map((version) => (
          <Card key={version.version_number}>
            <div className="editorial-card__meta">
              <strong>Версия {version.version_number}</strong>
              <span>{new Date(version.created_at).toLocaleString()}</span>
            </div>
            <p>
              {version.actor.full_name} · {version.reason}
            </p>
            <p>
              Изменено: {version.changed_fields.join(", ") || "первый снимок"}
            </p>
            <details>
              <summary>Снимок</summary>
              <pre className="version-json">
                {JSON.stringify(version.snapshot, null, 2)}
              </pre>
            </details>
          </Card>
        ))}
      </div>
    </div>
  );
}
