import { useQuery } from "@tanstack/react-query";

import { api } from "../../shared/api";
import { roleLabel, t } from "../../shared/i18n";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

export function ProfilePage() {
  const profile = useQuery({ queryKey: ["me"], queryFn: api.me });
  if (profile.isPending) return <PageState kind="loading" />;
  if (profile.isError) return <PageState error={profile.error} />;

  const user = profile.data;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("profile")}</p>
          <h1>{user.full_name}</h1>
          <p className="page-description">{t("homeDescription")}</p>
        </div>
      </header>
      <Card>
        <dl className="definition-list">
          <div>
            <dt>{t("portalId")}</dt>
            <dd>{user.portal_id}</dd>
          </div>
          <div>
            <dt>{t("email")}</dt>
            <dd>{user.email || t("notSpecified")}</dd>
          </div>
          <div>
            <dt>{t("phone")}</dt>
            <dd>{user.phone || t("notSpecified")}</dd>
          </div>
          <div>
            <dt>{t("position")}</dt>
            <dd>{user.job_title || t("notSpecified")}</dd>
          </div>
          <div>
            <dt>{t("department")}</dt>
            <dd>{user.org_unit?.name || t("noOrganization")}</dd>
          </div>
          <div>
            <dt>{t("roles")}</dt>
            <dd className="badge-row">
              {user.module_roles.map((role) => (
                <Badge key={role}>{roleLabel(role)}</Badge>
              ))}
            </dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
