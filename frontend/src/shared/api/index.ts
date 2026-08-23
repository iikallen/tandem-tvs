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
  employees: string[];
  module_roles: string[];
}

export interface PublicationSummary {
  id: string;
  slug: string;
  title: string;
  summary: string;
  category: Category;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  published_at: string;
  cover: null;
  view_count: number;
  comment_count: number;
  reaction_count: number;
  is_read: boolean;
}

export interface PublicationDetail extends PublicationSummary {
  body: RichTextNode;
}

export interface Comment {
  id: string;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  body: string | null;
  status: "ACTIVE" | "DELETED";
  created_at: string;
  updated_at: string;
  edited_at: string | null;
  deleted_at: string | null;
}

export interface ReactionSummary {
  total: number;
  counts: Record<string, number>;
  mine: string[];
}

export interface EditorialPublication {
  id: string;
  slug: string;
  title: string;
  summary: string;
  body: RichTextNode;
  category: string;
  author: Pick<Me, "portal_id" | "full_name" | "job_title">;
  status: "DRAFT" | "PUBLISHED";
  published_at: string | null;
  audience: Audience;
  created_at: string;
  updated_at: string;
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
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "api_error",
      payload?.error?.message ?? response.statusText,
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
  employees: (search: string) =>
    request<Employee[]>(
      `/api/v1/organization/employees?search=${encodeURIComponent(search)}`,
    ),
  categories: () => request<Category[]>("/api/v1/news/categories"),
  news: (filters: NewsFilters, cursor?: string) =>
    request<CursorPage<PublicationSummary>>(newsUrl(filters, cursor)),
  publication: (id: string) =>
    request<PublicationDetail>(`/api/v1/news/${encodeURIComponent(id)}`),
  comments: (id: string, cursor?: string) =>
    request<CursorPage<Comment>>(
      `/api/v1/news/${encodeURIComponent(id)}/comments${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
  createComment: (id: string, body: string) =>
    request<Comment>(
      `/api/v1/news/${encodeURIComponent(id)}/comments`,
      "POST",
      { body },
    ),
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
  realtimeTicket: (publicationId: string) =>
    request<{ ticket: string; expires_in: number }>(
      "/api/v1/realtime/tickets",
      "POST",
      {
        publication_id: publicationId,
      },
    ),
  editorial: () =>
    request<CursorPage<EditorialPublication>>("/api/v1/editorial/publications"),
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
};
