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
  type MediaAsset,
  type ReactionType,
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

const reactionLabels: Record<ReactionType, { icon: string; label: string }> = {
  LIKE: { icon: "👍", label: t("reactionLike") },
  CELEBRATE: { icon: "🎉", label: t("reactionCelebrate") },
  SUPPORT: { icon: "🤝", label: t("reactionSupport") },
  INSIGHTFUL: { icon: "💡", label: t("reactionInsightful") },
  THANKS: { icon: "🙏", label: t("reactionThanks") },
};

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
        <ImageGallery
          assets={
            item.media
              ?.filter(
                (usage) =>
                  usage.asset.kind === "IMAGE" && usage.purpose === "BODY",
              )
              .map((usage) => usage.asset) ?? []
          }
        />
      </Card>
      {item.acknowledgement_required ? (
        <Acknowledgement
          publicationId={publicationId}
          acknowledged={item.is_acknowledged}
        />
      ) : null}
      <RealtimeState status={realtime} />
      {item.reactions_enabled !== false ? (
        <ReactionBar publicationId={publicationId} />
      ) : null}
      <Comments
        publicationId={publicationId}
        enabled={item.comments_enabled !== false}
        attachmentsEnabled={item.category.comment_attachments_enabled === true}
      />
    </article>
  );
}

function ImageGallery({ assets }: { assets: MediaAsset[] }) {
  const [selected, setSelected] = useState<MediaAsset>();
  if (!assets.length) return null;
  return (
    <>
      <div className="image-gallery" aria-label={t("imageGallery")}>
        {assets.map((asset) => (
          <button
            type="button"
            key={asset.id}
            onClick={() => setSelected(asset)}
            aria-label={t("openImage", { name: asset.original_name })}
          >
            <img src={asset.content_url} alt={asset.original_name} />
          </button>
        ))}
      </div>
      {selected ? (
        <div className="gallery-dialog" role="dialog" aria-modal="true">
          <button
            type="button"
            className="gallery-dialog__close"
            onClick={() => setSelected(undefined)}
            aria-label={t("close")}
          >
            ×
          </button>
          <img src={selected.content_url} alt={selected.original_name} />
        </div>
      ) : null}
    </>
  );
}

function Acknowledgement({
  publicationId,
  acknowledged,
}: {
  publicationId: string;
  acknowledged: boolean;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => api.acknowledge(publicationId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["publication", publicationId],
      }),
  });
  return (
    <Card className="acknowledgement-card">
      <div>
        <strong>
          {acknowledged ? t("acknowledgementDone") : t("acknowledgementTitle")}
        </strong>
        <p>{t("acknowledgementDescription")}</p>
      </div>
      <button
        type="button"
        className="button"
        disabled={acknowledged || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {acknowledged ? t("acknowledged") : t("acknowledge")}
      </button>
    </Card>
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
    mutationFn: async (type: ReactionType) => {
      const current = reactions.data?.mine[0];
      if (current === type) await api.deleteReaction(publicationId, type);
      else await api.putReaction(publicationId, type);
    },
    onSettled: () => invalidatePublicationCaches(queryClient, publicationId),
  });
  if (reactions.isPending) return <PageState kind="loading" />;
  if (reactions.isError) return <PageState error={reactions.error} />;
  const enabled = reactions.data.enabled_types ?? ["LIKE"];
  return (
    <Card className="reaction-bar">
      <h2>{t("reactions")}</h2>
      <div className="reaction-buttons">
        {enabled.map((type) => {
          const active = reactions.data.mine.includes(type);
          const meta = reactionLabels[type];
          return (
            <button
              className="reaction-button"
              type="button"
              key={type}
              aria-pressed={active}
              aria-label={`${meta.label}: ${reactions.data.counts[type] ?? 0}`}
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(type)}
            >
              <span aria-hidden="true">{meta.icon}</span> {meta.label} ·{" "}
              {reactions.data.counts[type] ?? 0}
            </button>
          );
        })}
      </div>
    </Card>
  );
}

function Comments({
  publicationId,
  enabled,
  attachmentsEnabled,
}: {
  publicationId: string;
  enabled: boolean;
  attachmentsEnabled: boolean;
}) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [sort, setSort] = useState<"recent" | "popular">("recent");
  const [replyTo, setReplyTo] = useState<Comment>();
  const [mentionSearch, setMentionSearch] = useState("");
  const [mentions, setMentions] = useState<string[]>([]);
  const [attachments, setAttachments] = useState<MediaAsset[]>([]);
  const comments = useInfiniteQuery({
    queryKey: ["comments", publicationId, sort],
    queryFn: ({ pageParam }) => api.comments(publicationId, pageParam, sort),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => cursorFromUrl(page.next),
  });
  const candidates = useQuery({
    queryKey: ["mention-candidates", publicationId, mentionSearch],
    queryFn: () => api.mentionCandidates(publicationId, mentionSearch),
    enabled: mentionSearch.trim().length >= 2,
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadCommentMedia(publicationId, file),
    onSuccess: (asset) => setAttachments((current) => [...current, asset]),
  });
  const create = useMutation({
    mutationFn: () =>
      api.createComment(publicationId, body, {
        reply_to: replyTo?.id,
        mentions,
        attachments: attachments.map((asset) => asset.id),
      }),
    onSuccess: async () => {
      setBody("");
      setReplyTo(undefined);
      setMentions([]);
      setAttachments([]);
      await invalidatePublicationCaches(queryClient, publicationId);
    },
  });
  const items = comments.data?.pages.flatMap((page) => page.results) ?? [];
  return (
    <section className="comments-section" aria-labelledby="comments-heading">
      <div className="section-heading">
        <h2 id="comments-heading">{t("comments")}</h2>
        <div className="segmented" aria-label={t("commentSorting")}>
          {(["recent", "popular"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={sort === value}
              onClick={() => setSort(value)}
            >
              {t(value === "recent" ? "recentComments" : "popularComments")}
            </button>
          ))}
        </div>
      </div>
      {enabled ? (
        <form
          className="comment-composer"
          onSubmit={(event) => {
            event.preventDefault();
            if (body.trim()) create.mutate();
          }}
        >
          {replyTo ? (
            <div className="reply-context">
              {t("replyingTo", { name: replyTo.author.full_name })}
              <button type="button" onClick={() => setReplyTo(undefined)}>
                {t("cancel")}
              </button>
            </div>
          ) : null}
          <label htmlFor="new-comment">{t("commentLabel")}</label>
          <textarea
            id="new-comment"
            maxLength={5000}
            value={body}
            placeholder={t("commentPlaceholder")}
            onChange={(event) => setBody(event.target.value)}
          />
          <div className="composer-tools">
            <label>
              {t("mentionEmployee")}
              <input
                value={mentionSearch}
                onChange={(event) => setMentionSearch(event.target.value)}
              />
            </label>
            {candidates.data?.length ? (
              <div className="mention-candidates">
                {candidates.data.map((candidate) => (
                  <button
                    type="button"
                    key={candidate.portal_id}
                    onClick={() => {
                      setMentions((current) =>
                        current.includes(candidate.portal_id)
                          ? current
                          : [...current, candidate.portal_id],
                      );
                      setBody(
                        (current) =>
                          `${current}${current ? " " : ""}@${candidate.full_name} `,
                      );
                      setMentionSearch("");
                    }}
                  >
                    @{candidate.full_name}
                  </button>
                ))}
              </div>
            ) : null}
            {attachmentsEnabled ? (
              <label className="file-button">
                {t("attachFile")}
                <input
                  type="file"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) upload.mutate(file);
                  }}
                />
              </label>
            ) : null}
          </div>
          {attachments.map((asset) => (
            <span className="attachment-chip" key={asset.id}>
              {asset.original_name}
            </span>
          ))}
          <div className="comment-composer__footer">
            <span>{t("commentCounter", { count: body.length })}</span>
            <button
              className="button"
              disabled={!body.trim() || create.isPending || upload.isPending}
            >
              {t("sendComment")}
            </button>
          </div>
          {create.isError ? <PageState error={create.error} /> : null}
          {upload.isError ? <PageState error={upload.error} /> : null}
        </form>
      ) : (
        <p className="discussion-closed">{t("discussionClosed")}</p>
      )}
      {comments.isPending ? (
        <PageState kind="loading" />
      ) : comments.isError ? (
        <PageState error={comments.error} />
      ) : items.length === 0 ? (
        <p className="comments-empty">{t("noComments")}</p>
      ) : (
        <div className="comment-list">
          {items.map((comment) => (
            <Thread
              key={comment.id}
              publicationId={publicationId}
              root={comment}
              onReply={setReplyTo}
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

function Thread({
  publicationId,
  root,
  onReply,
}: {
  publicationId: string;
  root: Comment;
  onReply: (comment: Comment) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const replies = useInfiniteQuery({
    queryKey: ["replies", publicationId, root.id],
    queryFn: ({ pageParam }) => api.replies(publicationId, root.id, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => cursorFromUrl(page.next),
    enabled: expanded,
  });
  const preview = root.preview_replies ?? [];
  const shown = expanded
    ? (replies.data?.pages.flatMap((page) => page.results) ?? preview)
    : preview;
  return (
    <div className="comment-thread">
      <CommentItem
        publicationId={publicationId}
        comment={root}
        onReply={onReply}
      />
      {shown.length ? (
        <div className="comment-replies">
          {shown.map((reply) => (
            <CommentItem
              publicationId={publicationId}
              comment={reply}
              onReply={onReply}
              key={reply.id}
            />
          ))}
        </div>
      ) : null}
      {root.reply_count > preview.length && !expanded ? (
        <button
          className="text-button"
          type="button"
          onClick={() => setExpanded(true)}
        >
          {t("showMoreReplies", { count: root.reply_count - preview.length })}
        </button>
      ) : null}
      {expanded && replies.hasNextPage ? (
        <button
          className="text-button"
          type="button"
          onClick={() => replies.fetchNextPage()}
        >
          {t("showMoreReplies", { count: "" })}
        </button>
      ) : null}
    </div>
  );
}

function CommentItem({
  publicationId,
  comment,
  onReply,
}: {
  publicationId: string;
  comment: Comment;
  onReply: (comment: Comment) => void;
}) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
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
  const report = useMutation({
    mutationFn: () =>
      api.reportComment(
        publicationId,
        comment.id,
        window.prompt(t("reportReason")) ?? "",
      ),
  });
  const own =
    (comment.author.id != null && me.data?.id === comment.author.id) ||
    (comment.author.portal_id != null &&
      me.data?.portal_id === comment.author.portal_id);
  const canEdit = comment.can_edit ?? own;
  const canDelete = comment.can_delete ?? own;
  const tombstone = comment.status !== "ACTIVE";
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
      {tombstone ? (
        <p className="comment-deleted">
          {comment.status === "HIDDEN"
            ? t("hiddenComment")
            : comment.status === "REMOVED"
              ? t("removedComment")
              : t("deletedComment")}
        </p>
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
        <>
          {comment.reply_to_author ? (
            <small>{t("replyTo", { name: comment.reply_to_author })}</small>
          ) : null}
          <p className="comment-body">{comment.body}</p>
          {comment.attachments?.length ? (
            <div className="comment-attachments">
              {comment.attachments.map((asset) => (
                <a key={asset.id} href={asset.content_url}>
                  {asset.original_name}
                </a>
              ))}
            </div>
          ) : null}
        </>
      )}
      {comment.edited_at && !tombstone ? (
        <small>{t("editedComment")}</small>
      ) : null}
      {!tombstone && !editing ? (
        <div className="comment-actions">
          <CommentReaction publicationId={publicationId} comment={comment} />
          <button
            className="text-button"
            type="button"
            onClick={() => onReply(comment)}
          >
            {t("reply")}
          </button>
          {canEdit ? (
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
          ) : null}
          {canDelete ? (
            <button
              className="text-button"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {t("deleteComment")}
            </button>
          ) : null}
          {!own ? (
            <button
              className="text-button"
              type="button"
              disabled={report.isPending}
              onClick={() => report.mutate()}
            >
              {t("report")}
            </button>
          ) : null}
        </div>
      ) : null}
      {update.isError ? <PageState error={update.error} /> : null}
      {remove.isError ? <PageState error={remove.error} /> : null}
    </article>
  );
}

function CommentReaction({
  publicationId,
  comment,
}: {
  publicationId: string;
  comment: Comment;
}) {
  const queryClient = useQueryClient();
  const summary = useQuery({
    queryKey: ["comment-reactions", comment.id],
    queryFn: () => api.commentReactions(publicationId, comment.id),
  });
  const mutation = useMutation({
    mutationFn: async () => {
      if (summary.data?.mine?.includes("LIKE"))
        await api.deleteCommentReaction(publicationId, comment.id, "LIKE");
      else await api.putCommentReaction(publicationId, comment.id, "LIKE");
    },
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: ["comment-reactions", comment.id],
      }),
  });
  const active = summary.data?.mine?.includes("LIKE") ?? false;
  return (
    <button
      className="text-button"
      type="button"
      aria-pressed={active}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      👍 {summary.data?.counts?.LIKE ?? comment.reaction_count ?? 0}
    </button>
  );
}
