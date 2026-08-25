export interface OrgUnitSummary {
  external_id: string;
  name: string;
  kind: string;
  parent_external_id: string | null;
}

export interface Me {
  id: number;
  username: string;
  portal_id: string | null;
  full_name: string;
  email: string;
  job_title: string;
  phone: string;
  avatar_url: string;
  org_unit: OrgUnitSummary | null;
  module_roles: string[];
  is_active: boolean;
  activated_at: string | null;
  access: {
    platform: string[];
    news: string[];
    messenger: string[];
  };
}

export interface AuthSession {
  authenticated: boolean;
  user: Me | null;
}

export interface MessengerPerson {
  id: number;
  username: string;
  full_name: string;
  job_title: string;
  avatar_url: string;
  org_unit_name: string | null;
}

export interface MessengerMembership {
  id?: number;
  user: MessengerPerson;
  role: "MEMBER" | "WRITER" | "ADMIN";
  joined_at: string;
  joined_sequence?: number;
  left_at?: string | null;
  left_sequence?: number | null;
  is_active?: boolean;
  last_delivered_sequence?: number;
  delivered_at?: string | null;
  last_read_sequence: number;
  read_at: string | null;
  notification_mode?: "ALL" | "MENTIONS" | "NONE";
}

export type MessengerReaction = {
  reaction_type: "LIKE" | "LOVE" | "LAUGH" | "WOW" | "SAD";
  count: number;
  mine: boolean;
};

export interface MessengerMessage {
  id: string;
  sequence: number;
  client_message_id: string;
  author: MessengerPerson;
  body: string;
  kind?: "CHAT" | "CHANNEL_POST" | "DISCUSSION";
  mention_all?: boolean;
  reply_to?: {
    id: string;
    author: MessengerPerson;
    body_preview: string;
    deleted_at: string | null;
  } | null;
  forwarded_snapshot?: {
    author_name: string;
    body: string;
    created_at: string;
  } | null;
  attachments?: MediaAsset[];
  reactions?: MessengerReaction[];
  edited_at?: string | null;
  deleted_at?: string | null;
  created_at: string;
  receipt: {
    delivered?: boolean;
    delivered_count?: number;
    read?: boolean;
    read_count: number;
    recipient_count: number;
  };
}

export interface MessengerConversation {
  id: string;
  type: "DIRECT" | "GROUP" | "CHANNEL";
  discussion_enabled?: boolean;
  title: string;
  peer?: MessengerPerson | null;
  member_count?: number;
  last_message_at: string | null;
  activity_at?: string;
  last_message:
    | MessengerMessage
    | {
        id: string;
        sequence: number;
        author_id: number;
        author_name: string;
        body_preview: string;
        created_at: string;
        deleted_at: string | null;
      }
    | null;
  unread_count: number;
  state?: {
    is_archived: boolean;
    pinned_at: string | null;
    muted_until: string | null;
    draft_body: string;
    draft_updated_at: string | null;
  };
  created_by_id?: number;
  last_sequence?: number;
  created_at?: string;
  members?: MessengerMembership[];
  pinned_messages?: Array<{
    id: string;
    sequence: number;
    author_id: number;
    author_name: string;
    body_preview: string;
    created_at: string;
    deleted_at: string | null;
  }>;
}

export interface MessengerMessagePage {
  messages: MessengerMessage[];
  has_more: boolean;
  next_before_sequence: number | null;
}

export interface PlatformUser extends Omit<Me, "org_unit"> {
  org_unit: number | null;
}

export interface UserSummary {
  id?: number;
  username?: string;
  portal_id: string | null;
  full_name: string;
  job_title: string;
}

export interface PositionGroup {
  external_id: string;
  name: string;
}

export interface Employee {
  id: number;
  portal_id: string | null;
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
  employees: number[];
  module_roles: string[];
  position_groups?: PositionGroup[];
}

export interface PublicationSummary {
  id: string;
  slug: string;
  title: string;
  summary: string;
  category: Category;
  author: UserSummary;
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
  author: UserSummary;
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
  actors?: Record<string, Employee[]>;
  enabled_types?: ReactionType[];
}

export type ReactionType =
  "LIKE" | "CELEBRATE" | "SUPPORT" | "INSIGHTFUL" | "THANKS";

export type NotificationType =
  | "NEW_PUBLICATION"
  | "ACK_REQUIRED"
  | "COMMENT_REPLY"
  | "COMMENT_MENTION"
  | "NEW_MESSAGE"
  | "MESSAGE_MENTION"
  | "CHAT_ADDED";

export interface Notification {
  id: string;
  notification_type: NotificationType;
  actor: Pick<UserSummary, "id" | "full_name"> | null;
  source_type: string;
  source_id: string;
  publication_id: string | null;
  conversation_id: string | null;
  occurrence_count: number;
  event_version: number;
  created_at: string;
  last_event_at: string;
  read_at: string | null;
  target_url: string;
}

export interface NotificationPreference {
  notification_type: NotificationType;
  in_app_enabled: boolean;
  push_enabled: boolean;
  email_enabled: boolean;
}

export interface NotificationSettings {
  enabled: boolean;
  preferences: NotificationPreference[];
}

export interface SearchResult {
  id: string | number;
  title: string;
  snippet: string;
  url: string;
  author?: string;
  avatar_url?: string;
  org_unit?: string | null;
}

export type GlobalSearchResults = Record<
  "publications" | "comments" | "messages" | "files" | "employees",
  SearchResult[]
>;

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
  author: UserSummary;
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
  actor: UserSummary;
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

let csrfToken = "";

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const response = await fetch("/api/v1/auth/csrf", {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new ApiError(response.status, "csrf_error", response.statusText);
  const payload = (await response.json()) as { csrf_token: string };
  csrfToken = payload.csrf_token;
  return csrfToken;
}

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
  const token = unsafe ? await ensureCsrf() : "";
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(unsafe ? { "X-CSRFToken": token } : {}),
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
  csrf: async () => {
    csrfToken = "";
    return ensureCsrf();
  },
  session: () => request<AuthSession>("/api/v1/auth/session"),
  login: async (username: string, password: string) => {
    const result = await request<{ user: Me; csrf_token: string }>(
      "/api/v1/auth/login",
      "POST",
      { username, password },
    );
    csrfToken = result.csrf_token;
    return result;
  },
  logout: async () => {
    await request<void>("/api/v1/auth/logout", "POST");
    csrfToken = "";
  },
  activate: (token: string, password: string, passwordConfirm: string) =>
    request<{ status: string }>("/api/v1/auth/activate", "POST", {
      token,
      password,
      password_confirm: passwordConfirm,
    }),
  requestPasswordReset: (email: string) =>
    request<{ detail: string }>("/api/v1/auth/password/reset/request", "POST", {
      email,
    }),
  resetPassword: (token: string, password: string, passwordConfirm: string) =>
    request<{ status: string }>("/api/v1/auth/password/reset/confirm", "POST", {
      token,
      password,
      password_confirm: passwordConfirm,
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/api/v1/auth/password/change", "POST", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  platformUsers: (search = "") =>
    request<PlatformUser[]>(
      `/api/v1/platform/users${search ? `?search=${encodeURIComponent(search)}` : ""}`,
    ),
  createPlatformUser: (data: Record<string, unknown>) =>
    request<PlatformUser>("/api/v1/platform/users", "POST", data),
  updatePlatformUser: (id: number, data: Record<string, unknown>) =>
    request<PlatformUser>(`/api/v1/platform/users/${id}`, "PATCH", data),
  grantAccess: (id: number, module: string, role: string) =>
    request<void>(
      `/api/v1/platform/users/${id}/grants/${module}/${role}`,
      "PUT",
    ),
  revokeAccess: (id: number, module: string, role: string) =>
    request<void>(
      `/api/v1/platform/users/${id}/grants/${module}/${role}`,
      "DELETE",
    ),
  createInvitation: (id: number) =>
    request<{ activation_url: string }>(
      `/api/v1/platform/users/${id}/invitation`,
      "POST",
    ),
  createAdminPasswordReset: (id: number) =>
    request<{ reset_url: string }>(
      `/api/v1/platform/users/${id}/password-reset`,
      "POST",
    ),
  messengerAccess: () =>
    request<{ allowed: boolean; implementation: string }>(
      "/api/v1/messenger/access",
    ),
  messengerPeople: (search = "") =>
    request<MessengerPerson[]>(
      `/api/v1/messenger/people${search ? `?search=${encodeURIComponent(search)}` : ""}`,
    ),
  messengerConversations: async (cursor?: string) => {
    const data = await request<
      CursorPage<MessengerConversation> | MessengerConversation[]
    >(
      `/api/v1/messenger/conversations${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    return Array.isArray(data)
      ? { next: null, previous: null, results: data }
      : data;
  },
  messengerConversation: (id: string) =>
    request<MessengerConversation>(
      `/api/v1/messenger/conversations/${encodeURIComponent(id)}`,
    ),
  updateMessengerChannelSettings: (id: string, discussionEnabled: boolean) =>
    request<MessengerConversation>(
      `/api/v1/messenger/conversations/${encodeURIComponent(id)}`,
      "PATCH",
      { discussion_enabled: discussionEnabled },
    ),
  createDirectConversation: (userId: number) =>
    request<MessengerConversation>(
      "/api/v1/messenger/conversations/direct",
      "POST",
      { user_id: userId },
    ),
  createGroupConversation: (title: string, memberIds: number[]) =>
    request<MessengerConversation>(
      "/api/v1/messenger/conversations/group",
      "POST",
      { title, member_ids: memberIds },
    ),
  createChannelConversation: (
    title: string,
    memberIds: number[],
    writerIds: number[],
    discussionEnabled: boolean,
  ) =>
    request<MessengerConversation>(
      "/api/v1/messenger/conversations/channel",
      "POST",
      {
        title,
        member_ids: memberIds,
        writer_ids: writerIds,
        discussion_enabled: discussionEnabled,
      },
    ),
  messengerMessages: (id: string, beforeSequence?: number) =>
    request<MessengerMessagePage>(
      `/api/v1/messenger/conversations/${encodeURIComponent(id)}/messages${beforeSequence ? `?before_sequence=${beforeSequence}&page_size=50` : ""}`,
    ),
  messengerMessageContext: async (
    conversationId: string,
    messageId: string,
  ) => {
    const data = await request<{
      before: MessengerMessage[];
      target: MessengerMessage;
      after: MessengerMessage[];
    }>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/context`,
    );
    return {
      messages: [...data.before, data.target, ...data.after],
      has_more: false,
      next_before_sequence: null,
    } satisfies MessengerMessagePage;
  },
  sendMessengerMessage: (
    conversationId: string,
    clientMessageId: string,
    body: string,
    options: {
      reply_to_id?: string | null;
      attachment_ids?: string[];
      forward_message_id?: string | null;
      kind?: "CHAT" | "CHANNEL_POST" | "DISCUSSION";
      mentioned_user_ids?: number[];
      mention_all?: boolean;
    } = {},
  ) =>
    request<MessengerMessage>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/messages`,
      "POST",
      { client_message_id: clientMessageId, body, ...options },
    ),
  editMessengerMessage: (messageId: string, body: string) =>
    request<MessengerMessage>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}`,
      "PATCH",
      { body },
    ),
  deleteMessengerMessage: (messageId: string) =>
    request<MessengerMessage>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}`,
      "DELETE",
    ),
  putMessengerReaction: (messageId: string, reactionType: string) =>
    request<MessengerMessage>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}/reaction`,
      "PUT",
      { reaction_type: reactionType },
    ),
  deleteMessengerReaction: (messageId: string) =>
    request<void>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}/reaction`,
      "DELETE",
    ),
  pinMessengerMessage: (messageId: string) =>
    request<void>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}/pin`,
      "PUT",
    ),
  unpinMessengerMessage: (messageId: string) =>
    request<void>(
      `/api/v1/messenger/messages/${encodeURIComponent(messageId)}/pin`,
      "DELETE",
    ),
  markMessengerRead: (conversationId: string, sequence: number) =>
    request<{ last_read_sequence: number; read_at: string | null }>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/read`,
      "POST",
      { sequence },
    ),
  markMessengerDelivered: (conversationId: string, sequence: number) =>
    request<{ last_delivered_sequence: number; delivered_at: string | null }>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/delivered`,
      "POST",
      { sequence },
    ),
  messengerMembers: (conversationId: string, page = 1) =>
    request<CursorPage<MessengerMembership>>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/members?page=${page}`,
    ),
  addMessengerMember: (conversationId: string, userId: number) =>
    request<MessengerMembership>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/members`,
      "POST",
      { user_id: userId },
    ),
  changeMessengerMemberRole: (
    conversationId: string,
    userId: number,
    role: "MEMBER" | "WRITER" | "ADMIN",
  ) =>
    request<MessengerMembership>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/members/${userId}`,
      "PATCH",
      { role },
    ),
  removeMessengerMember: (conversationId: string, userId: number) =>
    request<void>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/members/${userId}`,
      "DELETE",
    ),
  leaveMessengerConversation: (conversationId: string) =>
    request<void>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/leave`,
      "POST",
    ),
  updateMessengerState: (
    conversationId: string,
    state: Record<string, unknown>,
  ) =>
    request<MessengerMembership>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/state`,
      "PATCH",
      state,
    ),
  uploadMessengerAttachment: (conversationId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<MediaAsset>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/attachments`,
      "POST",
      data,
    );
  },
  searchMessengerMessages: (conversationId: string, query: string) =>
    request<{ results: MessengerMessage[] }>(
      `/api/v1/messenger/conversations/${encodeURIComponent(conversationId)}/search?q=${encodeURIComponent(query)}`,
    ),
  messengerRealtimeTicket: () =>
    request<{ ticket: string; expires_in: number }>(
      "/api/v1/realtime/tickets",
      "POST",
      { scope: "MESSENGER" },
    ),
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
    request<Employee[]>(
      `/api/v1/news/${id}/mention-candidates?search=${encodeURIComponent(search)}`,
    ),
  acknowledge: (id: string) =>
    request<{ acknowledged_at: string }>(
      `/api/v1/news/${id}/acknowledgement`,
      "POST",
    ),
  notifications: (unread = false, cursor?: string) =>
    request<CursorPage<Notification>>(
      `/api/v1/notifications?unread=${unread}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  unreadNotificationCount: () =>
    request<{ unread_count: number }>("/api/v1/notifications/unread-count"),
  readNotification: (id: string) =>
    request<void>(`/api/v1/notifications/${id}/read`, "POST"),
  readAllNotifications: () =>
    request<{ updated: number }>("/api/v1/notifications/read-all", "POST"),
  notificationSettings: () =>
    request<NotificationSettings>("/api/v1/notification-settings"),
  updateNotificationSettings: (data: Partial<NotificationSettings>) =>
    request<NotificationSettings>(
      "/api/v1/notification-settings",
      "PATCH",
      data,
    ),
  notificationRealtimeTicket: () =>
    request<{ ticket: string; expires_in: number }>(
      "/api/v1/realtime/tickets",
      "POST",
      { scope: "NOTIFICATIONS" },
    ),
  pushConfig: () =>
    request<{ enabled: boolean; vapid_public_key: string }>(
      "/api/v1/push/config",
    ),
  savePushSubscription: (data: {
    endpoint: string;
    p256dh: string;
    auth: string;
  }) => request<void>("/api/v1/push/subscriptions", "POST", data),
  globalSearch: (query: string) =>
    request<GlobalSearchResults>(
      `/api/v1/search?q=${encodeURIComponent(query)}`,
    ),
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
