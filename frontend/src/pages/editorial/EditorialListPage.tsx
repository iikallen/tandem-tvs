import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, type EditorialPublication, type Me } from "../../shared/api";
import { t } from "../../shared/i18n";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { ConfirmDialog } from "../../shared/ui/ConfirmDialog";
import { PageState } from "../../shared/ui/PageState";
import { EditorialGuard } from "./EditorialGuard";

const statuses: Array<EditorialPublication["status"] | "ALL"> = [
  "ALL",
  "DRAFT",
  "IN_REVIEW",
  "SCHEDULED",
  "PUBLISHED",
  "UNPUBLISHED",
  "ARCHIVED",
];

const labels: Record<string, string> = {
  ALL: t("all"),
  DRAFT: t("filterDrafts"),
  IN_REVIEW: t("filterInReview"),
  SCHEDULED: t("filterScheduled"),
  PUBLISHED: t("filterPublished"),
  UNPUBLISHED: t("filterUnpublished"),
  ARCHIVED: t("filterArchived"),
};

export function EditorialListPage() {
  return (
    <EditorialGuard>
      <EditorialList />
    </EditorialGuard>
  );
}

export function EditorialReviewPage() {
  return (
    <EditorialGuard>
      <EditorialList initialStatus="IN_REVIEW" review />
    </EditorialGuard>
  );
}

function EditorialList({
  initialStatus = "ALL",
  review = false,
}: {
  initialStatus?: EditorialPublication["status"] | "ALL";
  review?: boolean;
}) {
  const [selectedStatus, setSelectedStatus] = useState(initialStatus);
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const publications = useQuery({
    queryKey: ["editorial", selectedStatus, review],
    queryFn: () =>
      review
        ? api.review()
        : api.editorial(selectedStatus === "ALL" ? undefined : selectedStatus),
  });
  if (me.isPending || publications.isPending)
    return <PageState kind="loading" />;
  if (me.isError) return <PageState error={me.error} />;
  if (publications.isError) return <PageState error={publications.error} />;
  const editor = isEditor(me.data);
  return (
    <div className="page-stack">
      <header className="page-header editorial-heading">
        <div>
          <p className="overline">{t("editorialSpace")}</p>
          <h1>{review ? t("reviewQueue") : t("publications")}</h1>
          <p className="page-description">{t("publicationsDescription")}</p>
        </div>
        <div className="button-row">
          <Link className="button" to="/editorial/publications/new">
            {t("newPublication")}
          </Link>
        </div>
      </header>
      {!review && (
        <div
          className="status-tabs"
          role="tablist"
          aria-label={t("publicationStatuses")}
        >
          {statuses.map((item) => (
            <button
              key={item}
              className={item === selectedStatus ? "is-active" : ""}
              type="button"
              role="tab"
              aria-selected={item === selectedStatus}
              onClick={() => setSelectedStatus(item)}
            >
              {labels[item]}
            </button>
          ))}
        </div>
      )}
      {publications.data.results.length === 0 ? (
        <div className="state">
          <div className="state__content">
            <h2>{t("noDrafts")}</h2>
          </div>
        </div>
      ) : (
        <div className="editorial-list">
          {publications.data.results.map((publication) => (
            <EditorialCard
              key={publication.id}
              publication={publication}
              editor={editor}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EditorialCard({
  publication,
  editor,
}: {
  publication: EditorialPublication;
  editor: boolean;
}) {
  const queryClient = useQueryClient();
  const [confirmAction, setConfirmAction] = useState<"unpublish" | "archive">();
  const action = useMutation({
    mutationFn: async (name: string) => {
      if (name === "duplicate") return api.duplicatePublication(publication.id);
      if (name === "pin") {
        const slot = Number(window.prompt(t("pinSlotPrompt"), "1"));
        if (!Number.isInteger(slot)) throw new Error(t("invalidPinSlot"));
        return api.pinPublication(publication.id, slot);
      }
      if (name === "unpin") return api.unpinPublication(publication.id);
      return api.transitionPublication(publication.id, name, {
        expected_revision: publication.edit_revision ?? 0,
      });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["editorial"] });
      await queryClient.invalidateQueries({ queryKey: ["news"] });
    },
  });
  return (
    <Card className="editorial-card">
      <div className="editorial-card__meta">
        <Badge
          tone={publication.status === "PUBLISHED" ? "success" : undefined}
        >
          {labels[publication.status]}
        </Badge>
        <span>rev. {publication.edit_revision ?? 0}</span>
      </div>
      <Link to={`/editorial/publications/${publication.id}`}>
        <h2>{publication.title}</h2>
        <p>{publication.summary}</p>
      </Link>
      <div className="button-row editorial-actions">
        <Link
          className="button button--secondary"
          to={`/editorial/publications/${publication.id}`}
        >
          {t("open")}
        </Link>
        <Link
          className="button button--secondary"
          to={`/editorial/publications/${publication.id}/versions`}
        >
          {t("versions")}
        </Link>
        <button
          type="button"
          className="button button--secondary"
          onClick={() => action.mutate("duplicate")}
        >
          {t("duplicate")}
        </button>
        {publication.status === "DRAFT" && (
          <button
            type="button"
            className="button button--secondary"
            onClick={() => action.mutate("submit-review")}
          >
            {t("submitReview")}
          </button>
        )}
        {editor && publication.status === "IN_REVIEW" && (
          <button
            type="button"
            className="button button--secondary"
            onClick={() => action.mutate("return-to-draft")}
          >
            {t("returnToDraft")}
          </button>
        )}
        {editor &&
          ["DRAFT", "IN_REVIEW", "UNPUBLISHED"].includes(
            publication.status,
          ) && (
            <button
              type="button"
              className="button"
              onClick={() => action.mutate("publish")}
            >
              {t("publish")}
            </button>
          )}
        {editor && publication.status === "PUBLISHED" && (
          <button
            type="button"
            className="button button--secondary"
            onClick={() =>
              action.mutate(publication.pin_slot ? "unpin" : "pin")
            }
          >
            {t(publication.pin_slot ? "unpin" : "pin")}
          </button>
        )}
        {editor && publication.status === "SCHEDULED" && (
          <button
            type="button"
            className="button button--secondary"
            onClick={() => action.mutate("cancel-schedule")}
          >
            {t("cancelSchedule")}
          </button>
        )}
        {editor && publication.status === "PUBLISHED" && (
          <button
            type="button"
            className="button button--danger"
            onClick={() => setConfirmAction("unpublish")}
          >
            {t("unpublish")}
          </button>
        )}
        {editor && publication.status === "UNPUBLISHED" && (
          <button
            type="button"
            className="button button--danger"
            onClick={() => setConfirmAction("archive")}
          >
            {t("archive")}
          </button>
        )}
      </div>
      {action.isError && (
        <p className="field-error" role="alert">
          {action.error.message}
        </p>
      )}
      <ConfirmDialog
        open={Boolean(confirmAction)}
        title={
          confirmAction === "archive"
            ? t("archiveQuestion")
            : t("unpublishQuestion")
        }
        consequence={
          confirmAction === "archive"
            ? t("archiveConsequence")
            : t("unpublishConsequence")
        }
        confirmLabel={
          confirmAction === "archive" ? t("archiveAction") : t("unpublish")
        }
        busy={action.isPending}
        onCancel={() => setConfirmAction(undefined)}
        onConfirm={() => {
          if (confirmAction)
            action.mutate(confirmAction, {
              onSuccess: () => setConfirmAction(undefined),
            });
        }}
      />
    </Card>
  );
}

function isEditor(me: Me) {
  return me.module_roles.some((role) =>
    ["editor", "admin", "administrator"].includes(role),
  );
}
