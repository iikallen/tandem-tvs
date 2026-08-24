export interface OrgUnitSummary {
  external_id: string;
  name: string;
  kind: string;
  parent_external_id: string | null;
}

export interface Me {
  portal_id: string;
  full_name: string;
  email: string;
  job_title: string;
  phone: string;
  avatar_url: string;
  org_unit: OrgUnitSummary | null;
  module_roles: string[];
}

export interface PositionGroup {
  external_id: string;
  name: string;
}

export interface Employee {
  portal_id: string;
  full_name: string;
  job_title: string;
  org_unit_external_id: string | null;
}

export interface Category {
  id: number;
  slug: string;
  name: string;
  sort_order: number;
  is_active?: boolean;
  comment_attachments_enabled?: boolean;
}

export interface Tag {
  id: number;
  slug: string;
  name: string;
  is_active: boolean;
}

export interface MediaAsset {
  id: string;
  original_name: string;
  mime_type: string;
  size: number;
  sha256: string;
  kind: "IMAGE" | "VIDEO" | "DOCUMENT";
  width: number | null;
  height: number | null;
  status: "READY" | "REJECTED";
  created_at: string;
  content_url: string;
}

export interface RichTextNode {
  type: string;
  text?: string;
  attrs?: Record<string, unknown>;
  marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
  content?: RichTextNode[];
}

export interface Audience {
  everyone: boolean;
  org_units: string[];
  org_unit_subtrees?: string[];
  employees: string[];
  module_roles: string[];
  position_groups?: PositionGroup[];
}

export interface PublicationSummary {
  id: string;
  slug: string;
  title: string;
  summary: string;
  category: Category;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  published_at: string;
  tags?: Tag[];
  cover: MediaAsset | null;
  pin_slot?: number | null;
  expires_at?: string | null;
  view_count: number;
  comment_count: number;
  reaction_count: number;
  is_read: boolean;
  comments_enabled: boolean;
  reactions_enabled: boolean;
  acknowledgement_required: boolean;
}

export interface PublicationDetail extends PublicationSummary {
  body: RichTextNode;
  media?: Array<{ asset: MediaAsset; purpose: string }>;
  is_acknowledged: boolean;
}

export interface Comment {
  id: string;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  body: string | null;
  status: "ACTIVE" | "DELETED" | "HIDDEN" | "REMOVED";
  thread_root: string | null;
  reply_to: string | null;
  reply_to_author: string | null;
  reply_count: number;
  reaction_count: number;
  preview_replies: Comment[];
  attachments: MediaAsset[];
  mentions: string[];
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
  edited_at: string | null;
  deleted_at: string | null;
}

export interface ReactionSummary {
  total: number;
  counts: Record<string, number>;
  mine: string[];
  actors?: Record<
    string,
    Array<Pick<Me, "portal_id" | "full_name" | "job_title">>
  >;
  enabled_types?: ReactionType[];
}

export type ReactionType =
  "LIKE" | "CELEBRATE" | "SUPPORT" | "INSIGHTFUL" | "THANKS";

export interface Notification {
  id: string;
  notification_type: "COMMENT_REPLY" | "COMMENT_MENTION";
  actor: Pick<Me, "portal_id" | "full_name" | "job_title">;
  publication_id: string;
  comment_id: string;
  created_at: string;
  read_at: string | null;
}

export interface EngagementSettings {
  comment_edit_window_minutes: number;
  comment_delete_window_minutes: number;
  enabled_reaction_types: ReactionType[];
  max_comment_attachments: number;
  max_comment_attachment_bytes: number;
  stop_words: Array<{ id: number; value: string; is_active: boolean }>;
  updated_at: string;
}

export interface PublicationAnalytics {
  publication_id: string;
  title: string;
  category: string;
  recipients: number;
  views: number;
  unique_views: number;
  reach_percent: string;
  comments: number;
  reactions: number;
  unique_engaged: number;
  engagement_percent: string;
  acknowledged: number;
  pending: number;
  acknowledgement_percent: string | null;
  departments: Array<{
    name: string;
    recipients: number;
    unique_views: number;
    reach_percent: string;
    acknowledged: number;
  }>;
}

export interface EditorialPublication {
  id: string;
  slug: string;
  title: string;
  summary: string;
  body: RichTextNode;
  category: string;
  tags?: string[];
  cover?: string | null;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  status:
    | "DRAFT"
    | "IN_REVIEW"
    | "SCHEDULED"
    | "PUBLISHED"
    | "UNPUBLISHED"
    | "ARCHIVED";
  published_at: string | null;
  scheduled_for?: string | null;
  expires_at?: string | null;
  unpublished_at?: string | null;
  archived_at?: string | null;
  edit_revision?: number;
  last_autosaved_at?: string | null;
  audience: Audience;
  media?: Array<{ asset: MediaAsset; purpose: string }>;
  pin_slot?: number | null;
  comments_enabled: boolean;
  reactions_enabled: boolean;
  acknowledgement_required: boolean;
  created_at: string;
  updated_at: string;
}

export interface PublicationVersion {
  version_number: number;
  actor: Pick<Me, "portal_id" | "full_name" | "job_title">;
  reason: string;
  snapshot: Record<string, unknown>;
  changed_fields: string[];
  content_hash: string;
  created_at: string;
}

export interface CursorPage<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface NewsFilters {
  q?: string;
  unread?: boolean;
  category?: string;
  author?: string;
  date_from?: string;
  date_to?: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public currentRevision?: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body === undefined || body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
    },
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: {
        code?: string;
        message?: string;
        current_revision?: number;
      };
    } | null;
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "api_error",
      payload?.error?.message ?? response.statusText,
      payload?.error?.current_revision,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function newsUrl(filters: NewsFilters, cursor?: string): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== false && value !== "") {
      params.set(key, String(value));
    }
  }
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  return `/api/v1/news${query ? `?${query}` : ""}`;
}

export function cursorFromUrl(url: string | null): string | undefined {
  return url
    ? (new URL(url).searchParams.get("cursor") ?? undefined)
    : undefined;
}

export const api = {
  me: () => request<Me>("/api/v1/me"),
  orgUnits: () => request<OrgUnitSummary[]>("/api/v1/organization/units"),
  positionGroups: () =>
    request<PositionGroup[]>("/api/v1/organization/position-groups"),
  employees: (search: string) =>
    request<Employee[]>(
      `/api/v1/organization/employees?search=${encodeURIComponent(search)}`,
    ),
  categories: () => request<Category[]>("/api/v1/news/categories"),
  pinned: () => request<PublicationSummary[]>("/api/v1/news/pinned"),
  news: (filters: NewsFilters, cursor?: string) =>
    request<CursorPage<PublicationSummary>>(newsUrl(filters, cursor)),
  publication: (id: string) =>
    request<PublicationDetail>(`/api/v1/news/${encodeURIComponent(id)}`),
  comments: (id: string, cursor?: string, sort = "recent") =>
    request<CursorPage<Comment>>(
      `/api/v1/news/${encodeURIComponent(id)}/comments${sort !== "recent" || cursor ? `?${sort !== "recent" ? `sort=${sort}` : ""}${sort !== "recent" && cursor ? "&" : ""}${cursor ? `cursor=${encodeURIComponent(cursor)}` : ""}` : ""}`,
    ),
  replies: (id: string, rootId: string, cursor?: string) =>
    request<CursorPage<Comment>>(
      `/api/v1/news/${encodeURIComponent(id)}/comments/${rootId}/replies${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  createComment: (
    id: string,
    body: string,
    options: {
      reply_to?: string;
      mentions?: string[];
      attachments?: string[];
    } = {},
  ) =>
    request<Comment>(
      `/api/v1/news/${encodeURIComponent(id)}/comments`,
      "POST",
      { body, ...options },
    ),
  uploadCommentMedia: (id: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<MediaAsset>(
      `/api/v1/news/${encodeURIComponent(id)}/comment-media`,
      "POST",
      data,
    );
  },
  updateComment: (publicationId: string, commentId: string, body: string) =>
    request<Comment>(
      `/api/v1/news/${encodeURIComponent(publicationId)}/comments/${encodeURIComponent(commentId)}`,
      "PATCH",
      { body },
    ),
  deleteComment: (publicationId: string, commentId: string) =>
    request<void>(
      `/api/v1/news/${encodeURIComponent(publicationId)}/comments/${encodeURIComponent(commentId)}`,
      "DELETE",
    ),
  reactions: (id: string) =>
    request<ReactionSummary>(
      `/api/v1/news/${encodeURIComponent(id)}/reactions`,
    ),
  putReaction: (id: string, type: string) =>
    request<{ id: string; reaction_type: string }>(
      `/api/v1/news/${encodeURIComponent(id)}/reactions/${encodeURIComponent(type)}`,
      "PUT",
    ),
  deleteReaction: (id: string, type: string) =>
    request<void>(
      `/api/v1/news/${encodeURIComponent(id)}/reactions/${encodeURIComponent(type)}`,
      "DELETE",
    ),
  commentReactions: (id: string, commentId: string) =>
    request<ReactionSummary>(
      `/api/v1/news/${id}/comments/${commentId}/reactions`,
    ),
  putCommentReaction: (id: string, commentId: string, type: string) =>
    request(
      `/api/v1/news/${id}/comments/${commentId}/reactions/${type}`,
      "PUT",
    ),
  deleteCommentReaction: (id: string, commentId: string, type: string) =>
    request<void>(
      `/api/v1/news/${id}/comments/${commentId}/reactions/${type}`,
      "DELETE",
    ),
  reportComment: (id: string, commentId: string, reason: string) =>
    request(`/api/v1/news/${id}/comments/${commentId}/reports`, "POST", {
      reason,
    }),
  mentionCandidates: (id: string, search: string) =>
    request<Array<Pick<Me, "portal_id" | "full_name" | "job_title">>>(
      `/api/v1/news/${id}/mention-candidates?search=${encodeURIComponent(search)}`,
    ),
  acknowledge: (id: string) =>
    request<{ acknowledged_at: string }>(
      `/api/v1/news/${id}/acknowledgement`,
      "POST",
    ),
  notifications: () => request<Notification[]>("/api/v1/notifications"),
  readNotification: (id: string) =>
    request<void>(`/api/v1/notifications/${id}/read`, "POST"),
  realtimeTicket: (publicationId: string) =>
    request<{ ticket: string; expires_in: number }>(
      "/api/v1/realtime/tickets",
      "POST",
      {
        publication_id: publicationId,
      },
    ),
  editorial: (status?: EditorialPublication["status"]) =>
    request<CursorPage<EditorialPublication>>(
      `/api/v1/editorial/publications${status ? `?status=${status}` : ""}`,
    ),
  review: () =>
    request<CursorPage<EditorialPublication>>("/api/v1/editorial/review"),
  editorialPublication: (id: string) =>
    request<EditorialPublication>(`/api/v1/editorial/publications/${id}`),
  createPublication: (data: unknown) =>
    request<EditorialPublication>(
      "/api/v1/editorial/publications",
      "POST",
      data,
    ),
  updatePublication: (id: string, data: unknown) =>
    request<EditorialPublication>(
      `/api/v1/editorial/publications/${id}`,
      "PATCH",
      data,
    ),
  publishPublication: (id: string) =>
    request<EditorialPublication>(
      `/api/v1/editorial/publications/${id}/publish`,
      "POST",
    ),
  transitionPublication: (
    id: string,
    action: string,
    data: Record<string, unknown> = {},
  ) =>
    request<EditorialPublication>(
      `/api/v1/editorial/publications/${id}/${action}`,
      "POST",
      data,
    ),
  duplicatePublication: (id: string) =>
    request<EditorialPublication>(
      `/api/v1/editorial/publications/${id}/duplicate`,
      "POST",
      {},
    ),
  versions: (id: string) =>
    request<PublicationVersion[]>(
      `/api/v1/editorial/publications/${id}/versions`,
    ),
  media: () => request<CursorPage<MediaAsset>>("/api/v1/editorial/media"),
  uploadMedia: (file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<MediaAsset>("/api/v1/editorial/media", "POST", data);
  },
  deleteMedia: (id: string) =>
    request<void>(`/api/v1/editorial/media/${id}`, "DELETE"),
  editorialCategories: () =>
    request<Category[]>("/api/v1/editorial/categories"),
  createCategory: (data: Partial<Category>) =>
    request<Category>("/api/v1/editorial/categories", "POST", data),
  updateCategory: (id: number, data: Partial<Category>) =>
    request<Category>(`/api/v1/editorial/categories/${id}`, "PATCH", data),
  tags: () => request<Tag[]>("/api/v1/editorial/tags"),
  createTag: (data: Partial<Tag>) =>
    request<Tag>("/api/v1/editorial/tags", "POST", data),
  updateTag: (id: number, data: Partial<Tag>) =>
    request<Tag>(`/api/v1/editorial/tags/${id}`, "PATCH", data),
  pinPublication: (id: string, slot: number) =>
    request<{ publication_id: string; slot: number }>(
      `/api/v1/news/${id}/pin`,
      "PUT",
      { slot },
    ),
  unpinPublication: (id: string) =>
    request<void>(`/api/v1/news/${id}/pin`, "DELETE"),
  engagementSettings: () =>
    request<EngagementSettings>("/api/v1/editorial/settings/engagement"),
  updateEngagementSettings: (data: Partial<EngagementSettings>) =>
    request<EngagementSettings>(
      "/api/v1/editorial/settings/engagement",
      "PATCH",
      data,
    ),
  createStopWord: (value: string) =>
    request<{ id: number; value: string; is_active: boolean }>(
      "/api/v1/editorial/settings/engagement/stop-words",
      "POST",
      { value },
    ),
  updateStopWord: (id: number, data: { is_active: boolean }) =>
    request(
      `/api/v1/editorial/settings/engagement/stop-words/${id}`,
      "PATCH",
      data,
    ),
  moderation: () =>
    request<{
      reports: Array<{
        id: string;
        comment: Comment;
        publication_title: string;
        created_at: string;
      }>;
      flags: Comment[];
    }>("/api/v1/editorial/moderation"),
  moderateComment: (id: string, action: "hide" | "restore" | "remove") =>
    request<Comment>(
      `/api/v1/editorial/moderation/comments/${id}/${action}`,
      "POST",
    ),
  resolveReport: (id: string) =>
    request<void>(`/api/v1/editorial/moderation/reports/${id}/resolve`, "POST"),
  analytics: () =>
    request<{ results: PublicationAnalytics[] }>("/api/v1/editorial/analytics"),
  publicationAnalytics: (id: string) =>
    request<PublicationAnalytics>(
      `/api/v1/editorial/publications/${id}/analytics`,
    ),
  restrictCommenting: (portalId: string, hours = 24) =>
    request(
      `/api/v1/editorial/moderation/users/${portalId}/restriction`,
      "POST",
      { hours },
    ),
  revokeRestriction: (portalId: string) =>
    request<void>(
      `/api/v1/editorial/moderation/users/${portalId}/restriction`,
      "DELETE",
    ),
  acknowledgements: (id: string, state: "acknowledged" | "pending") =>
    request<
      Array<{
        portal_id: string;
        full_name: string;
        email: string;
        department: string;
        acknowledged_at: string | null;
      }>
    >(`/api/v1/editorial/publications/${id}/acknowledgements?status=${state}`),
};
