import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  api,
  cursorFromUrl,
  type Notification,
  type NotificationType,
} from "../../shared/api";
import { t, type TranslationKey } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";

const labels: Record<NotificationType, TranslationKey> = {
  NEW_PUBLICATION: "notificationNewPublication",
  ACK_REQUIRED: "notificationAckRequired",
  COMMENT_REPLY: "notificationCommentReply",
  COMMENT_MENTION: "notificationCommentMention",
  NEW_MESSAGE: "notificationNewMessage",
  MESSAGE_MENTION: "notificationMessageMention",
  CHAT_ADDED: "notificationChatAdded",
};

function actorName(item: Notification) {
  return item.actor?.full_name || t("notificationSystem");
}

export function NotificationsPage() {
  const [unread, setUnread] = useState(false);
  const queryClient = useQueryClient();
  const notifications = useInfiniteQuery({
    queryKey: ["notifications", unread],
    queryFn: ({ pageParam }) => api.notifications(unread, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => cursorFromUrl(page.next),
  });
  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["notifications"] }),
      queryClient.invalidateQueries({ queryKey: ["notification-count"] }),
    ]);
  };
  const read = useMutation({
    mutationFn: api.readNotification,
    onSuccess: invalidate,
  });
  const readAll = useMutation({
    mutationFn: api.readAllNotifications,
    onSuccess: invalidate,
  });
  if (notifications.isPending) return <PageState kind="loading" />;
  if (notifications.isError) return <PageState error={notifications.error} />;
  const rows = notifications.data.pages.flatMap((page) => page.results);
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <h1>{t("notifications")}</h1>
          <p className="page-description">{t("notificationsDescription")}</p>
        </div>
        <div className="button-row">
          <Link
            className="button button--secondary"
            to="/settings/notifications"
          >
            {t("notificationSettings")}
          </Link>
          <button
            className="button button--secondary"
            type="button"
            onClick={() => readAll.mutate()}
            disabled={readAll.isPending}
          >
            {t("markAllRead")}
          </button>
        </div>
      </header>
      <div
        className="segmented"
        role="group"
        aria-label={t("notificationFilter")}
      >
        <button
          type="button"
          aria-pressed={!unread}
          onClick={() => setUnread(false)}
        >
          {t("all")}
        </button>
        <button
          type="button"
          aria-pressed={unread}
          onClick={() => setUnread(true)}
        >
          {t("unread")}
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="page-description">{t("notificationsEmpty")}</p>
      ) : (
        rows.map((item) => (
          <Card
            className={
              item.read_at
                ? "notification-card"
                : "notification-card notification-card--unread"
            }
            key={item.id}
          >
            <div>
              <strong>{actorName(item)}</strong>
              <p>{t(labels[item.notification_type])}</p>
              {item.occurrence_count > 1 && (
                <small>
                  {t("notificationOccurrences", {
                    count: item.occurrence_count,
                  })}
                </small>
              )}
              <time dateTime={item.last_event_at}>
                {new Date(item.last_event_at).toLocaleString("ru-RU")}
              </time>
            </div>
            <Link
              className="button button--secondary"
              to={item.target_url}
              onClick={() => {
                if (!item.read_at) read.mutate(item.id);
              }}
            >
              {t("open")}
            </Link>
          </Card>
        ))
      )}
      {notifications.hasNextPage && (
        <button
          className="button button--secondary"
          type="button"
          disabled={notifications.isFetchingNextPage}
          onClick={() => notifications.fetchNextPage()}
        >
          {t("loadMore")}
        </button>
      )}
    </div>
  );
}
