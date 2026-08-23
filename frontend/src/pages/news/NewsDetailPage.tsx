import {
  type QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  api,
  cursorFromUrl,
  type Comment,
  type ReactionSummary,
} from "../../shared/api";
import { t } from "../../shared/i18n";
import { Badge } from "../../shared/ui/Badge";
import { Card } from "../../shared/ui/Card";
import { PageState } from "../../shared/ui/PageState";
import { RichTextRenderer } from "../../shared/ui/RichTextRenderer";
import {
  usePublicationRealtime,
  type RealtimeStatus as Status,
} from "./usePublicationRealtime";

function invalidatePublicationCaches(
  queryClient: QueryClient,
  publicationId: string,
) {
  return Promise.all([
    queryClient.invalidateQueries({
      queryKey: ["publication", publicationId],
    }),
    queryClient.invalidateQueries({
      queryKey: ["comments", publicationId],
    }),
    queryClient.invalidateQueries({
      queryKey: ["reactions", publicationId],
    }),
    queryClient.invalidateQueries({ queryKey: ["news"] }),
  ]);
}

export function NewsDetailPage() {
  const { publicationId = "" } = useParams();
  const publication = useQuery({
    queryKey: ["publication", publicationId],
    queryFn: () => api.publication(publicationId),
  });
  const realtime = usePublicationRealtime(publicationId);
  if (publication.isPending) return <PageState kind="loading" />;
  if (publication.isError) return <PageState error={publication.error} />;
  const item = publication.data;
  return (
    <article className="page-stack publication-detail">
      <Link className="back-link" to="/news">
        ← {t("allNews")}
      </Link>
      <header>
        <Badge>{item.category.name}</Badge>
        <h1>{item.title}</h1>
        <p className="page-description">{item.summary}</p>
        <p className="publication-meta">
          {item.author.full_name} ·{" "}
          {new Date(item.published_at).toLocaleDateString("ru-RU")} ·{" "}
          {t("views", { count: item.view_count })}
        </p>
      </header>
      <Card>
        <RichTextRenderer document={item.body} />
      </Card>
      <RealtimeState status={realtime} />
      <ReactionBar publicationId={publicationId} />
      <Comments publicationId={publicationId} />
    </article>
  );
}

function RealtimeState({ status }: { status: Status }) {
  const label =
    status === "connected"
      ? t("realtimeConnected")
      : status === "reconnecting"
        ? t("realtimeReconnecting")
        : t("realtimeStopped");
  return (
    <p className={`realtime-status realtime-status--${status}`}>{label}</p>
  );
}

function ReactionBar({ publicationId }: { publicationId: string }) {
  const queryClient = useQueryClient();
  const reactions = useQuery({
    queryKey: ["reactions", publicationId],
    queryFn: () => api.reactions(publicationId),
  });
  const mutation = useMutation({
    mutationFn: async (active: boolean) => {
      if (active) await api.deleteReaction(publicationId, "LIKE");
      else await api.putReaction(publicationId, "LIKE");
    },
    onMutate: async (active) => {
      await queryClient.cancelQueries({
        queryKey: ["reactions", publicationId],
      });
      const previous = queryClient.getQueryData<ReactionSummary>([
        "reactions",
        publicationId,
      ]);
      if (previous) {
        const delta = active ? -1 : 1;
        queryClient.setQueryData<ReactionSummary>(
          ["reactions", publicationId],
          {
            total: Math.max(0, previous.total + delta),
            counts: {
              ...previous.counts,
              LIKE: Math.max(0, (previous.counts.LIKE ?? 0) + delta),
            },
            mine: active
              ? previous.mine.filter((type) => type !== "LIKE")
              : ["LIKE"],
          },
        );
      }
      return previous;
    },
    onError: (_error, _active, previous) => {
      if (previous)
        queryClient.setQueryData(["reactions", publicationId], previous);
    },
    onSettled: () => invalidatePublicationCaches(queryClient, publicationId),
  });
  if (reactions.isPending) return <PageState kind="loading" />;
  if (reactions.isError) return <PageState error={reactions.error} />;
  const active = reactions.data.mine.includes("LIKE");
  return (
    <Card className="reaction-bar">
      <h2>{t("reactions")}</h2>
      <button
        className="reaction-button"
        type="button"
        aria-pressed={active}
        disabled={mutation.isPending}
        onClick={() => mutation.mutate(active)}
      >
        <span aria-hidden="true">♥</span> {t("like")} ·{" "}
        {reactions.data.counts.LIKE ?? 0}
      </button>
    </Card>
  );
}

function Comments({ publicationId }: { publicationId: string }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const comments = useInfiniteQuery({
    queryKey: ["comments", publicationId],
    queryFn: ({ pageParam }) => api.comments(publicationId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => cursorFromUrl(page.next),
  });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const create = useMutation({
    mutationFn: () => api.createComment(publicationId, body),
    onSuccess: async () => {
      setBody("");
      await invalidatePublicationCaches(queryClient, publicationId);
    },
  });
  const items = comments.data?.pages.flatMap((page) => page.results) ?? [];
  return (
    <section className="comments-section" aria-labelledby="comments-heading">
      <h2 id="comments-heading">{t("comments")}</h2>
      <form
        className="comment-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (body.trim()) create.mutate();
        }}
      >
        <label htmlFor="new-comment">{t("commentLabel")}</label>
        <textarea
          id="new-comment"
          maxLength={5000}
          value={body}
          placeholder={t("commentPlaceholder")}
          onChange={(event) => setBody(event.target.value)}
        />
        <div className="comment-composer__footer">
          <span>{t("commentCounter", { count: body.length })}</span>
          <button
            className="button"
            disabled={!body.trim() || create.isPending}
          >
            {t("sendComment")}
          </button>
        </div>
        {create.isError ? <PageState error={create.error} /> : null}
      </form>
      {comments.isPending ? (
        <PageState kind="loading" />
      ) : comments.isError ? (
        <PageState error={comments.error} />
      ) : items.length === 0 ? (
        <p className="comments-empty">{t("noComments")}</p>
      ) : (
        <div className="comment-list">
          {items.map((comment) => (
            <CommentItem
              key={comment.id}
              publicationId={publicationId}
              comment={comment}
              own={comment.author.portal_id === me.data?.portal_id}
            />
          ))}
        </div>
      )}
      {comments.hasNextPage ? (
        <button
          className="button button--secondary"
          disabled={comments.isFetchingNextPage}
          onClick={() => comments.fetchNextPage()}
        >
          {comments.isFetchingNextPage
            ? t("loadingMore")
            : t("loadMoreComments")}
        </button>
      ) : null}
    </section>
  );
}

function CommentItem({
  publicationId,
  comment,
  own,
}: {
  publicationId: string;
  comment: Comment;
  own: boolean;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [body, setBody] = useState("");
  const invalidate = () =>
    invalidatePublicationCaches(queryClient, publicationId);
  const update = useMutation({
    mutationFn: () => api.updateComment(publicationId, comment.id, body),
    onSuccess: async () => {
      setEditing(false);
      await invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteComment(publicationId, comment.id),
    onSuccess: invalidate,
  });
  return (
    <article className="comment-item">
      <header>
        <div>
          <strong>{comment.author.full_name}</strong>
          <span>{comment.author.job_title}</span>
        </div>
        <time dateTime={comment.created_at}>
          {new Date(comment.created_at).toLocaleString("ru-RU")}
        </time>
      </header>
      {comment.status === "DELETED" ? (
        <p className="comment-deleted">{t("deletedComment")}</p>
      ) : editing ? (
        <form
          className="comment-edit"
          onSubmit={(event) => {
            event.preventDefault();
            if (body.trim()) update.mutate();
          }}
        >
          <label className="sr-only" htmlFor={`comment-${comment.id}`}>
            {t("commentLabel")}
          </label>
          <textarea
            id={`comment-${comment.id}`}
            maxLength={5000}
            value={body}
            onChange={(event) => setBody(event.target.value)}
          />
          <div className="comment-actions">
            <button
              className="button"
              disabled={!body.trim() || update.isPending}
            >
              {t("saveComment")}
            </button>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setEditing(false)}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : (
        <p className="comment-body">{comment.body}</p>
      )}
      {comment.edited_at && comment.status === "ACTIVE" ? (
        <small>{t("editedComment")}</small>
      ) : null}
      {own && comment.status === "ACTIVE" && !editing ? (
        <div className="comment-actions">
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setBody(comment.body ?? "");
              setEditing(true);
            }}
          >
            {t("editComment")}
          </button>
          <button
            className="text-button"
            type="button"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            {t("deleteComment")}
          </button>
        </div>
      ) : null}
      {update.isError ? <PageState error={update.error} /> : null}
      {remove.isError ? <PageState error={remove.error} /> : null}
    </article>
  );
}
