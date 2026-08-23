import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const id = "00000000-0000-0000-0000-000000003001";
const me = {
  portal_id: "employee-1",
  full_name: "Алия Байжанова",
  email: "a@example.invalid",
  job_title: "Специалист",
  phone: "",
  avatar_url: "",
  org_unit: null,
  module_roles: ["employee"],
};
const publication = {
  id,
  slug: "stage-3",
  title: "Stage 3",
  summary: "Realtime",
  category: { id: 1, slug: "company", name: "Компания", sort_order: 0 },
  author: { portal_id: "author-1", full_name: "Автор", job_title: "Редактор" },
  published_at: "2026-08-23T09:00:00Z",
  cover: null,
  view_count: 1,
  comment_count: 0,
  reaction_count: 0,
  is_read: true,
  body: {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text: "Body" }] }],
  },
};

function response(body: unknown, status = 200): Response {
  return status === 204
    ? new Response(null, { status })
    : new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
}

class FakeWebSocket {
  static OPEN = 1;
  readyState = FakeWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    window.setTimeout(() => this.onopen?.(), 0);
  }
  close() {}
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

test("creates a comment and toggles LIKE with accessible controls", async () => {
  window.history.pushState({}, "", `/news/${id}`);
  let comments: unknown[] = [];
  let liked = false;
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/me")) return response(me);
      if (url.endsWith("/api/v1/realtime/tickets"))
        return response({ ticket: "ticket", expires_in: 30 });
      if (url.endsWith(`/api/v1/news/${id}/comments`)) {
        if (init?.method === "POST") {
          comments = [
            {
              id: "comment-1",
              author: me,
              body: "Новый комментарий",
              status: "ACTIVE",
              created_at: "2026-08-23T10:00:00Z",
              updated_at: "2026-08-23T10:00:00Z",
              edited_at: null,
              deleted_at: null,
            },
          ];
          return response(comments[0], 201);
        }
        return response({ next: null, previous: null, results: comments });
      }
      if (url.endsWith(`/api/v1/news/${id}/reactions`))
        return response({
          total: liked ? 1 : 0,
          counts: { LIKE: liked ? 1 : 0 },
          mine: liked ? ["LIKE"] : [],
        });
      if (url.endsWith(`/api/v1/news/${id}/reactions/LIKE`)) {
        liked = init?.method === "PUT";
        return liked
          ? response({ id: "reaction-1", reaction_type: "LIKE" }, 201)
          : response(null, 204);
      }
      return response(publication);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);

  const composer = await screen.findByLabelText("Комментарий");
  await userEvent.type(composer, "Новый комментарий");
  await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
  expect(await screen.findByText("Новый комментарий")).toBeVisible();

  const like = screen.getByRole("button", { name: /Нравится/ });
  expect(like).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(like);
  await waitFor(() => expect(like).toHaveAttribute("aria-pressed", "true"));
  expect((await axe(container)).violations).toHaveLength(0);
});

test("shows edit controls only for the current employee's active comment", async () => {
  window.history.pushState({}, "", `/news/${id}`);
  const other = { ...me, portal_id: "author-1", full_name: "Другой сотрудник" };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/me")) return response(me);
      if (url.endsWith("/api/v1/realtime/tickets"))
        return response({ ticket: "ticket", expires_in: 30 });
      if (url.endsWith(`/comments`))
        return response({
          next: null,
          previous: null,
          results: [
            {
              id: "own",
              author: me,
              body: "Свой",
              status: "ACTIVE",
              created_at: "2026-08-23T10:00:00Z",
              updated_at: "2026-08-23T10:00:00Z",
              edited_at: null,
              deleted_at: null,
            },
            {
              id: "other",
              author: other,
              body: "Чужой",
              status: "ACTIVE",
              created_at: "2026-08-23T10:01:00Z",
              updated_at: "2026-08-23T10:01:00Z",
              edited_at: null,
              deleted_at: null,
            },
          ],
        });
      if (url.endsWith(`/reactions`))
        return response({ total: 0, counts: {}, mine: [] });
      return response(publication);
    }),
  );
  vi.stubGlobal("WebSocket", FakeWebSocket);
  render(<App />);
  expect(await screen.findByText("Свой")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "Редактировать" })).toHaveLength(
    1,
  );
  expect(screen.getAllByRole("button", { name: "Удалить" })).toHaveLength(1);
});
