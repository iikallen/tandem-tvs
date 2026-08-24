import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const id = "00000000-0000-0000-0000-000000005001";
const employee = {
  portal_id: "employee-1",
  full_name: "Алия Байжанова",
  email: "a@example.invalid",
  job_title: "Специалист",
  phone: "",
  avatar_url: "",
  org_unit: null,
  module_roles: ["employee"],
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
  constructor() {
    window.setTimeout(() => this.onopen?.(), 0);
  }
  close() {}
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

test("renders acknowledgement, threaded replies and configured reactions", async () => {
  window.history.pushState({}, "", `/news/${id}`);
  let acknowledged = false;
  const root = {
    id: "00000000-0000-0000-0000-000000005010",
    author: employee,
    body: "Корневой комментарий",
    status: "ACTIVE",
    thread_root: null,
    reply_to: null,
    reply_to_author: null,
    reply_count: 1,
    reaction_count: 0,
    preview_replies: [
      {
        id: "00000000-0000-0000-0000-000000005011",
        author: { ...employee, portal_id: "editor-1", full_name: "Редактор" },
        body: "Ответ в ветке",
        status: "ACTIVE",
        thread_root: "00000000-0000-0000-0000-000000005010",
        reply_to: "00000000-0000-0000-0000-000000005010",
        reply_to_author: "Алия Байжанова",
        reply_count: 0,
        reaction_count: 0,
        preview_replies: [],
        attachments: [],
        mentions: [],
        can_edit: false,
        can_delete: false,
        created_at: "2026-08-24T08:01:00Z",
        updated_at: "2026-08-24T08:01:00Z",
        edited_at: null,
        deleted_at: null,
      },
    ],
    attachments: [],
    mentions: [],
    can_edit: true,
    can_delete: true,
    created_at: "2026-08-24T08:00:00Z",
    updated_at: "2026-08-24T08:00:00Z",
    edited_at: null,
    deleted_at: null,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/me")) return response(employee);
      if (url.endsWith("/api/v1/realtime/tickets"))
        return response({ ticket: "ticket", expires_in: 30 });
      if (url.includes("/comments?") || url.endsWith("/comments"))
        return response({ next: null, previous: null, results: [root] });
      if (url.includes("/comments/") && url.endsWith("/reactions"))
        return response({
          total: 0,
          counts: {},
          mine: [],
          enabled_types: ["LIKE"],
        });
      if (url.endsWith(`/news/${id}/reactions`))
        return response({
          total: 2,
          counts: { LIKE: 1, INSIGHTFUL: 1 },
          mine: [],
          enabled_types: ["LIKE", "INSIGHTFUL"],
        });
      if (
        url.endsWith(`/news/${id}/acknowledgement`) &&
        init?.method === "POST"
      ) {
        acknowledged = true;
        return response({ acknowledged_at: "2026-08-24T09:00:00Z" }, 201);
      }
      return response({
        id,
        slug: "stage-5",
        title: "Stage 5",
        summary: "Engagement",
        category: {
          id: 1,
          slug: "company",
          name: "Компания",
          sort_order: 0,
          comment_attachments_enabled: true,
        },
        author: employee,
        published_at: "2026-08-24T07:00:00Z",
        cover: null,
        view_count: 1,
        comment_count: 2,
        reaction_count: 2,
        is_read: true,
        comments_enabled: true,
        reactions_enabled: true,
        acknowledgement_required: true,
        is_acknowledged: acknowledged,
        body: { type: "doc", content: [] },
        media: [],
      });
    }),
  );
  const { container } = render(<App />);
  expect(await screen.findByText("Корневой комментарий")).toBeVisible();
  expect(screen.getByText("Ответ в ветке")).toBeVisible();
  expect(screen.getByRole("button", { name: /Полезно/ })).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить ознакомление" }),
  );
  await waitFor(() => expect(acknowledged).toBe(true));
  expect((await axe(container)).violations).toHaveLength(0);
});

test("shows editorial analytics with exact values and CSV action", async () => {
  window.history.pushState({}, "", "/editorial/analytics");
  const editor = {
    ...employee,
    portal_id: "editor-1",
    module_roles: ["editor"],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/me")) return response(editor);
      return response({
        results: [
          {
            publication_id: id,
            title: "Регламент VPN",
            category: "Разработка",
            recipients: 10,
            views: 7,
            unique_views: 7,
            reach_percent: "70.0",
            comments: 3,
            reactions: 4,
            unique_engaged: 5,
            engagement_percent: "50.0",
            acknowledged: 6,
            pending: 4,
            acknowledgement_percent: "60.0",
            departments: [],
          },
        ],
      });
    }),
  );
  render(<App />);
  expect(await screen.findByText("Регламент VPN")).toBeVisible();
  expect(screen.getByText("70.0%")).toBeVisible();
  expect(screen.getByRole("link", { name: "Экспорт CSV" })).toHaveAttribute(
    "href",
    "/api/v1/editorial/analytics.csv",
  );
});
