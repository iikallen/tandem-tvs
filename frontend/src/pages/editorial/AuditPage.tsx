import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

export function AuditPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const audit = useQuery({
    queryKey: ["editorial-audit"],
    queryFn: api.audit,
    enabled: me.data?.access.news.includes("ADMIN") === true,
  });
  if (me.isPending) return <PageState kind="loading" />;
  if (me.isError) return <PageState error={me.error} />;
  if (!me.data.access.news.includes("ADMIN")) {
    return <Navigate to="/editorial/publications" replace />;
  }
  if (audit.isPending) return <PageState kind="loading" />;
  if (audit.isError) return <PageState error={audit.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{t("auditLog")}</h1>
          <p className="page-description">{t("auditLogDescription")}</p>
        </div>
      </header>
      {audit.data.results.length ? (
        <div className="audit-list">
          {audit.data.results.map((event) => (
            <Card className="audit-event" key={event.id}>
              <header>
                <div>
                  <strong>{event.event_type}</strong>
                  <span>
                    {event.target_type} · {event.target_id || "—"}
                  </span>
                </div>
                <time dateTime={event.created_at}>
                  {new Date(event.created_at).toLocaleString("ru-RU")}
                </time>
              </header>
              <p>{t("auditActor", { name: event.actor.full_name })}</p>
              <div className="audit-states">
                <section>
                  <h2>{t("auditBefore")}</h2>
                  <pre>{formatState(event.previous_state)}</pre>
                </section>
                <section>
                  <h2>{t("auditAfter")}</h2>
                  <pre>{formatState(event.new_state)}</pre>
                </section>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <p>{t("auditLogEmpty")}</p>
        </Card>
      )}
    </div>
  );
}

function formatState(state: Record<string, unknown>): string {
  return Object.keys(state).length ? JSON.stringify(state, null, 2) : "—";
}
