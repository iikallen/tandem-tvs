import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { api, type PlatformUser } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

const defaultGrants = [
  { module: "NEWS", role: "MEMBER" },
  { module: "MESSENGER", role: "MEMBER" },
];

const editableGrants = [
  { module: "PLATFORM", role: "ADMIN" },
  { module: "NEWS", role: "MEMBER" },
  { module: "NEWS", role: "AUTHOR" },
  { module: "NEWS", role: "EDITOR" },
  { module: "NEWS", role: "MODERATOR" },
  { module: "NEWS", role: "ADMIN" },
  { module: "MESSENGER", role: "MEMBER" },
  { module: "MESSENGER", role: "ADMIN" },
] as const;

export function PlatformUsersPage() {
  const [search, setSearch] = useState("");
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [issuedLink, setIssuedLink] = useState("");
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: ["platform-users", search],
    queryFn: () => api.platformUsers(search),
  });
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["platform-users"] });
  const create = useMutation({
    mutationFn: () =>
      api.createPlatformUser({
        username,
        full_name: fullName,
        email,
        grants: defaultGrants,
      }),
    onSuccess: (user) => {
      setUsername("");
      setFullName("");
      setEmail("");
      refresh();
      invite.mutate(user.id);
    },
  });
  const invite = useMutation({
    mutationFn: (id: number) => api.createInvitation(id),
    onSuccess: ({ activation_url }) =>
      setIssuedLink(`${location.origin}${activation_url}`),
  });
  const reset = useMutation({
    mutationFn: (id: number) => api.createAdminPasswordReset(id),
    onSuccess: ({ reset_url }) =>
      setIssuedLink(`${location.origin}${reset_url}`),
  });
  const toggle = useMutation({
    mutationFn: (user: PlatformUser) =>
      api.updatePlatformUser(user.id, { is_active: !user.is_active }),
    onSuccess: refresh,
  });
  const updateGrant = useMutation({
    mutationFn: ({
      user,
      module,
      role,
      assigned,
    }: {
      user: PlatformUser;
      module: string;
      role: string;
      assigned: boolean;
    }) =>
      assigned
        ? api.revokeAccess(user.id, module, role)
        : api.grantAccess(user.id, module, role),
    onSuccess: refresh,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  if (users.isPending) return <PageState kind="loading" />;
  if (users.isError) return <PageState error={users.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("platform")}</p>
          <h1>{t("userManagement")}</h1>
          <p>{t("userManagementDescription")}</p>
        </div>
      </header>
      <Card>
        <form className="user-create-grid" onSubmit={submit}>
          <label>
            {t("username")}
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            {t("fullName")}
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </label>
          <label>
            {t("email")}
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button
            className="button button--primary"
            disabled={create.isPending}
          >
            {t("createUser")}
          </button>
        </form>
        {issuedLink && (
          <label className="issued-link">
            {t("oneTimeLink")}
            <input
              readOnly
              value={issuedLink}
              onFocus={(e) => e.currentTarget.select()}
            />
          </label>
        )}
      </Card>
      <label className="search-field">
        {t("searchUsers")}
        <input value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      <div className="user-list">
        {users.data.map((user) => (
          <Card className="user-row" key={user.id}>
            <div>
              <strong>{user.full_name}</strong>
              <small>
                @{user.username} · {user.email || t("notSpecified")}
              </small>
            </div>
            <div className="badge-row">
              {Object.entries(user.access).flatMap(([module, roles]) =>
                roles.map((role) => (
                  <Badge key={`${module}-${role}`}>
                    {module.toUpperCase()} {role}
                  </Badge>
                )),
              )}
              <Badge>
                {user.is_active
                  ? user.activated_at
                    ? t("active")
                    : t("pendingActivation")
                  : t("disabled")}
              </Badge>
            </div>
            <div className="action-row">
              <button
                className="button button--secondary"
                onClick={() => invite.mutate(user.id)}
              >
                {t("sendInvitation")}
              </button>
              <button
                className="button button--secondary"
                onClick={() => reset.mutate(user.id)}
              >
                {t("createResetLink")}
              </button>
              <button
                className="button button--danger"
                onClick={() => toggle.mutate(user)}
              >
                {user.is_active ? t("disable") : t("enable")}
              </button>
            </div>
            <details className="role-editor">
              <summary>{t("changeRoles")}</summary>
              <div className="role-editor__grid">
                {editableGrants.map(({ module, role }) => {
                  const assigned =
                    user.access[
                      module.toLowerCase() as keyof PlatformUser["access"]
                    ].includes(role);
                  return (
                    <button
                      className="button button--secondary"
                      type="button"
                      aria-pressed={assigned}
                      disabled={updateGrant.isPending}
                      key={`${module}-${role}`}
                      onClick={() =>
                        updateGrant.mutate({ user, module, role, assigned })
                      }
                    >
                      {module} {role} ·{" "}
                      {assigned ? t("revokeRole") : t("grantRole")}
                    </button>
                  );
                })}
              </div>
              {updateGrant.isError && (
                <p className="form-error" role="alert">
                  {t("accessUpdateFailed")}
                </p>
              )}
            </details>
          </Card>
        ))}
      </div>
    </div>
  );
}
