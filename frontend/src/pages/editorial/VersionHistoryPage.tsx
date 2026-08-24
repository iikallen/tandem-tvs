import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
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
          <p className="overline">{t("editorial")}</p>
          <h1>{t("versionHistory")}</h1>
        </div>
      </header>
      <div className="version-list">
        {versions.data.map((version) => (
          <Card key={version.version_number}>
            <div className="editorial-card__meta">
              <strong>
                {t("versionNumber", { number: version.version_number })}
              </strong>
              <span>{new Date(version.created_at).toLocaleString()}</span>
            </div>
            <p>
              {version.actor.full_name} · {version.reason}
            </p>
            <p>
              {t("changedFields", {
                fields: version.changed_fields.join(", ") || t("firstSnapshot"),
              })}
            </p>
            <details>
              <summary>{t("snapshot")}</summary>
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
