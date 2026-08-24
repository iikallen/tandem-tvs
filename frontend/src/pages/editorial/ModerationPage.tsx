import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Comment } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

export function ModerationPage() {
  return (
    <EditorialGuard>
      <ModerationContent />
    </EditorialGuard>
  );
}

function ModerationContent() {
  const queryClient = useQueryClient();
  const queue = useQuery({ queryKey: ["moderation"], queryFn: api.moderation });
  const moderate = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: string;
      action: "hide" | "restore" | "remove";
    }) => api.moderateComment(id, action),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["moderation"] }),
  });
  const resolve = useMutation({
    mutationFn: api.resolveReport,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["moderation"] }),
  });
  const restrict = useMutation({
    mutationFn: (portalId: string) => api.restrictCommenting(portalId),
  });
  if (queue.isPending) return <PageState kind="loading" />;
  if (queue.isError) return <PageState error={queue.error} />;
  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{t("moderation")}</h1>
          <p className="page-description">{t("moderationDescription")}</p>
        </div>
      </header>
      {queue.data.reports.length === 0 && queue.data.flags.length === 0 ? (
        <p className="page-description">{t("moderationEmpty")}</p>
      ) : null}
      {queue.data.reports.map((report) => (
        <ModerationCard
          key={report.id}
          comment={report.comment}
          title={report.publication_title}
          onAction={(action) =>
            moderate.mutate({ id: report.comment.id, action })
          }
          onResolve={() => resolve.mutate(report.id)}
          onRestrict={() => restrict.mutate(report.comment.author.portal_id)}
        />
      ))}
      {queue.data.flags.map((comment) => (
        <ModerationCard
          key={`flag-${comment.id}`}
          comment={comment}
          title={t("stopWordFlag")}
          onAction={(action) => moderate.mutate({ id: comment.id, action })}
          onRestrict={() => restrict.mutate(comment.author.portal_id)}
        />
      ))}
    </div>
  );
}

function ModerationCard({
  comment,
  title,
  onAction,
  onResolve,
  onRestrict,
}: {
  comment: Comment;
  title: string;
  onAction: (action: "hide" | "restore" | "remove") => void;
  onResolve?: () => void;
  onRestrict: () => void;
}) {
  return (
    <Card className="moderation-card">
      <div>
        <span className="overline">{title}</span>
        <h2>{comment.author.full_name}</h2>
        <p>{comment.body ?? t("moderatedPlaceholder")}</p>
      </div>
      <div className="comment-actions">
        {comment.status === "HIDDEN" ? (
          <button
            className="button button--secondary"
            onClick={() => onAction("restore")}
          >
            {t("restore")}
          </button>
        ) : (
          <button
            className="button button--secondary"
            onClick={() => onAction("hide")}
          >
            {t("hide")}
          </button>
        )}
        <button
          className="button button--danger"
          onClick={() => onAction("remove")}
        >
          {t("remove")}
        </button>
        {onResolve ? (
          <button className="text-button" onClick={onResolve}>
            {t("resolveReport")}
          </button>
        ) : null}
        <button className="text-button" onClick={onRestrict}>
          {t("restrict24Hours")}
        </button>
      </div>
    </Card>
  );
}
