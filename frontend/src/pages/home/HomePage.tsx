import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../shared/api";
import { roleLabel, t, unitKindLabel } from "../../shared/i18n";
import { Avatar } from "../../shared/ui/Avatar";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { EditIcon, NewsIcon, UserIcon, UsersIcon } from "../../shared/ui/icons";
import { PageState } from "../../shared/ui/PageState";

export function HomePage() {
  const profile = useQuery({ queryKey: ["me"], queryFn: api.me });
  if (profile.isPending) return <PageState kind="loading" />;
  if (profile.isError) return <PageState error={profile.error} />;

  const user = profile.data;
  const canEdit = user.module_roles.some((role) =>
    ["author", "editor", "admin", "administrator"].includes(role),
  );
  const shortcuts = [
    { to: "/news", label: t("news"), icon: NewsIcon },
    { to: "/employees", label: t("employees"), icon: UsersIcon },
    { to: "/profile", label: t("profile"), icon: UserIcon },
    ...(canEdit
      ? [
          {
            to: "/editorial/publications",
            label: t("editorial"),
            icon: EditIcon,
          },
        ]
      : []),
  ];
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("stage")}</p>
          <h1>{t("greeting", { name: user.full_name.split(" ")[0] })}</h1>
          <p className="page-description">{t("homeDescription")}</p>
        </div>
        <Badge tone="success">{t("ssoConnected")}</Badge>
      </header>
      <div className="dashboard-grid">
        <Card className="profile-hero profile-hero--dashboard">
          <Avatar name={user.full_name} imageUrl={user.avatar_url} size="lg" />
          <div className="profile-hero__identity">
            <p className="card-kicker">{t("profile")}</p>
            <h2>{user.full_name}</h2>
            <p>{user.job_title || t("notSpecified")}</p>
            <div className="badge-row">
              {user.module_roles.map((role) => (
                <Badge key={role}>{roleLabel(role)}</Badge>
              ))}
            </div>
          </div>
        </Card>
        <Card className="quick-links">
          <div className="card-heading">
            <div>
              <p className="card-kicker">{t("workspace")}</p>
              <h2>{t("quickLinks")}</h2>
            </div>
            <p>{t("quickLinksDescription")}</p>
          </div>
          <div className="quick-links__grid">
            {shortcuts.map(({ to, label, icon: Icon }) => (
              <Link className="quick-link" to={to} key={to}>
                <span className="quick-link__icon">
                  <Icon />
                </span>
                <strong>{label}</strong>
              </Link>
            ))}
          </div>
        </Card>
      </div>
      <div className="summary-grid">
        <Card title={t("contactDetails")}>
          <dl className="definition-list">
            <div>
              <dt>{t("email")}</dt>
              <dd>{user.email || t("notSpecified")}</dd>
            </div>
            <div>
              <dt>{t("phone")}</dt>
              <dd>{user.phone || t("notSpecified")}</dd>
            </div>
          </dl>
        </Card>
        <Card title={t("organization")}>
          <dl className="definition-list">
            <div>
              <dt>{t("department")}</dt>
              <dd>{user.org_unit?.name || t("noOrganization")}</dd>
            </div>
            <div>
              <dt>{t("unitType")}</dt>
              <dd>
                {user.org_unit
                  ? unitKindLabel(user.org_unit.kind)
                  : t("notSpecified")}
              </dd>
            </div>
          </dl>
        </Card>
      </div>
    </div>
  );
}
