import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: api.notifications,
  });
  const read = useMutation({
    mutationFn: api.readNotification,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  if (notifications.isPending) return <PageState kind="loading" />;
  if (notifications.isError) return <PageState error={notifications.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>{t("notifications")}</h1>
          <p className="page-description">{t("notificationsDescription")}</p>
        </div>
      </header>
      {notifications.data.length === 0 ? (
        <p className="page-description">{t("notificationsEmpty")}</p>
      ) : (
        notifications.data.map((item) => (
          <Card
            className={
              item.read_at
                ? "notification-card"
                : "notification-card notification-card--unread"
            }
            key={item.id}
          >
            <div>
              <strong>{item.actor.full_name}</strong>
              <p>
                {t(
                  item.notification_type === "COMMENT_MENTION"
                    ? "mentionedYou"
                    : "repliedToYou",
                )}
              </p>
              <time dateTime={item.created_at}>
                {new Date(item.created_at).toLocaleString("ru-RU")}
              </time>
            </div>
            <Link
              className="button button--secondary"
              to={`/news/${item.publication_id}`}
              onClick={() => {
                if (!item.read_at) read.mutate(item.id);
              }}
            >
              {t("open")}
            </Link>
          </Card>
        ))
      )}
    </div>
  );
}
