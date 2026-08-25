import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../shared/api";
import { t, type TranslationKey } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

const sectionLabels: Record<string, TranslationKey> = {
  publications: "searchPublications",
  comments: "searchComments",
  messages: "searchMessages",
  files: "searchFiles",
  employees: "searchEmployeesSection",
};

export function GlobalSearchPage() {
  const [params] = useSearchParams();
  const query = params.get("q")?.trim() || "";
  const results = useQuery({
    queryKey: ["global-search", query],
    queryFn: () => api.globalSearch(query),
    enabled: Boolean(query),
  });
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>{t("globalSearch")}</h1>
          <p className="page-description">
            {query ? t("searchResultsFor", { query }) : t("searchStartHint")}
          </p>
        </div>
      </header>
      {results.isPending && query && <PageState kind="loading" />}
      {results.isError && <PageState error={results.error} />}
      {results.data &&
        Object.entries(results.data).map(([section, rows]) => (
          <section className="search-section" key={section}>
            <h2>{t(sectionLabels[section])}</h2>
            {rows.length ? (
              <div className="search-results">
                {rows.map((row) => (
                  <Card key={`${section}-${row.id}`}>
                    <Link to={row.url} className="search-result-link">
                      <strong>{row.title}</strong>
                      {row.snippet && <p>{row.snippet}</p>}
                    </Link>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="page-description">{t("nothingFound")}</p>
            )}
          </section>
        ))}
    </div>
  );
}
