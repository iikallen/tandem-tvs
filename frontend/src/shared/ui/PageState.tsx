import { ApiError } from "../api";
import { t } from "../i18n";
import { AlertIcon, UsersIcon } from "./icons";

export function PageState({
  kind,
  error,
}: {
  kind?: "loading" | "empty";
  error?: unknown;
}) {
  if (kind === "loading") {
    return (
      <div className="state" role="status">
        <div className="state__content">
          <div className="state__icon">
            <span className="spinner" />
          </div>
          <h2>{t("loading")}</h2>
          <p>{t("loadingDescription")}</p>
        </div>
      </div>
    );
  }
  if (kind === "empty") {
    return (
      <div className="state">
        <div className="state__content">
          <div className="state__icon">
            <UsersIcon />
          </div>
          <h2>{t("emptyEmployees")}</h2>
          <p>{t("emptyEmployeesDescription")}</p>
        </div>
      </div>
    );
  }

  const apiError = error instanceof ApiError ? error : null;
  const blocked = apiError?.code === "portal_account_blocked";
  const unauthorized = apiError?.status === 401;
  const unavailable =
    apiError?.status === 503 || apiError?.code === "portal_unavailable";
  const title = blocked
    ? t("blocked")
    : unauthorized
      ? t("unauthorized")
      : unavailable
        ? t("unavailable")
        : t("error");
  const description = blocked
    ? t("blockedDescription")
    : unauthorized
      ? t("unauthorizedDescription")
      : unavailable
        ? t("unavailableDescription")
        : t("errorDescription");

  return (
    <div className="state" role="alert">
      <div className="state__content">
        <div className="state__icon">
          <AlertIcon />
        </div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}
