import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, type PublicationAnalytics } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

export function AnalyticsPage() {
  return (
    <EditorialGuard>
      <AnalyticsContent />
    </EditorialGuard>
  );
}

function AnalyticsContent() {
  const analytics = useQuery({
    queryKey: ["analytics"],
    queryFn: api.analytics,
  });
  const [selected, setSelected] = useState<PublicationAnalytics>();
  if (analytics.isPending) return <PageState kind="loading" />;
  if (analytics.isError) return <PageState error={analytics.error} />;
  const totals = analytics.data.results.reduce(
    (sum, item) => ({
      recipients: sum.recipients + item.recipients,
      views: sum.views + item.unique_views,
      comments: sum.comments + item.comments,
      reactions: sum.reactions + item.reactions,
    }),
    { recipients: 0, views: 0, comments: 0, reactions: 0 },
  );
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{t("analytics")}</h1>
          <p className="page-description">{t("analyticsDescription")}</p>
        </div>
        <a
          className="button button--secondary"
          href="/api/v1/editorial/analytics.csv"
        >
          {t("exportCsv")}
        </a>
      </header>
      <div className="metric-grid">
        <Metric label={t("recipients")} value={totals.recipients} />
        <Metric label={t("uniqueViews")} value={totals.views} />
        <Metric label={t("commentsMetric")} value={totals.comments} />
        <Metric label={t("reactions")} value={totals.reactions} />
      </div>
      <Card className="table-card">
        <table>
          <thead>
            <tr>
              <th>{t("publication")}</th>
              <th>{t("recipients")}</th>
              <th>{t("reach")}</th>
              <th>{t("engagement")}</th>
              <th>{t("acknowledged")}</th>
            </tr>
          </thead>
          <tbody>
            {analytics.data.results.map((item) => (
              <tr key={item.publication_id}>
                <td>
                  <button
                    className="text-button"
                    onClick={() => setSelected(item)}
                  >
                    {item.title}
                  </button>
                  <small>{item.category}</small>
                </td>
                <td>{item.recipients}</td>
                <td>{item.reach_percent}%</td>
                <td>{item.engagement_percent}%</td>
                <td>
                  {item.acknowledgement_percent === null
                    ? "—"
                    : `${item.acknowledgement_percent}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {selected ? (
        <PublicationStats
          item={selected}
          onClose={() => setSelected(undefined)}
        />
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </Card>
  );
}

function PublicationStats({
  item,
  onClose,
}: {
  item: PublicationAnalytics;
  onClose: () => void;
}) {
  const [state, setState] = useState<"acknowledged" | "pending">("pending");
  const people = useQuery({
    queryKey: ["acknowledgements", item.publication_id, state],
    queryFn: () => api.acknowledgements(item.publication_id, state),
  });
  return (
    <aside className="stats-panel" aria-label={t("publicationStats")}>
      <button
        className="stats-panel__close"
        onClick={onClose}
        aria-label={t("close")}
      >
        ×
      </button>
      <h2>{item.title}</h2>
      <div className="metric-grid metric-grid--compact">
        <Metric label={t("recipients")} value={item.recipients} />
        <Metric label={t("uniqueViews")} value={item.unique_views} />
        <Metric label={t("commentsMetric")} value={item.comments} />
        <Metric label={t("reactions")} value={item.reactions} />
      </div>
      <div className="segmented">
        <button
          aria-pressed={state === "acknowledged"}
          onClick={() => setState("acknowledged")}
        >
          {t("acknowledgedCount", { count: item.acknowledged })}
        </button>
        <button
          aria-pressed={state === "pending"}
          onClick={() => setState("pending")}
        >
          {t("pendingCount", { count: item.pending })}
        </button>
      </div>
      <a
        href={`/api/v1/editorial/publications/${item.publication_id}/acknowledgements.csv?status=${state}`}
      >
        {t("exportCsv")}
      </a>
      {people.isPending ? (
        <PageState kind="loading" />
      ) : (
        people.data?.map((person) => (
          <div className="person-row" key={person.portal_id}>
            <strong>{person.full_name}</strong>
            <span>{person.department}</span>
          </div>
        ))
      )}
    </aside>
  );
}
