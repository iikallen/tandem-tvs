import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Avatar } from "../../shared/ui/Avatar";
import { Card } from "../../shared/ui/Card";
import { CloseIcon, SearchIcon } from "../../shared/ui/icons";
import { PageState } from "../../shared/ui/PageState";

export function EmployeeDirectoryPage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const employees = useQuery({
    queryKey: ["employees", query],
    queryFn: () => api.employees(query),
  });

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("organization")}</p>
          <h1>{t("employeeDirectory")}</h1>
          <p className="page-description">
            {t("employeeDirectoryDescription")}
          </p>
        </div>
      </header>
      <div className="filter-bar">
        <label className="search-field">
          <span className="sr-only">{t("search")}</span>
          <SearchIcon />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("searchEmployees")}
          />
          {search && (
            <button
              className="clear-button"
              type="button"
              onClick={() => setSearch("")}
              aria-label={t("clearSearch")}
            >
              <CloseIcon />
            </button>
          )}
        </label>
        {employees.data && (
          <span className="employee-count">
            {t("employeeCount", { count: employees.data.length })}
          </span>
        )}
      </div>
      {employees.isPending ? (
        <PageState kind="loading" />
      ) : employees.isError ? (
        <PageState error={employees.error} />
      ) : employees.data.length === 0 ? (
        <PageState kind="empty" />
      ) : (
        <div className="employee-list">
          {employees.data.map((employee) => (
            <Card className="employee-card" key={employee.portal_id}>
              <Avatar
                name={employee.full_name}
                imageUrl={employee.avatar_url}
              />
              <div className="employee-card__body">
                <h2>{employee.full_name}</h2>
                <div className="employee-card__meta">
                  <span>{employee.job_title || t("notSpecified")}</span>
                  <span>{employee.email || t("notSpecified")}</span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
