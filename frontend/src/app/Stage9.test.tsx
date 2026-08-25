import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import type { Me, NotificationPreference } from "../shared/api";
import { App } from "./App";

const me: Me = {
  id: 1,
  username: "aliya",
  portal_id: null,
  full_name: "Алия Байжанова",
  email: "aliya@example.invalid",
  job_title: "Разработчик",
  phone: "",
  avatar_url: "",
  org_unit: null,
  module_roles: ["employee"],
  is_active: true,
  activated_at: "2026-08-25T08:00:00Z",
  access: { platform: [], news: ["MEMBER"], messenger: ["MEMBER"] },
};

const preference: NotificationPreference = {
  notification_type: "NEW_MESSAGE",
  in_app_enabled: true,
  push_enabled: false,
  email_enabled: false,
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
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close() {}
}

function stage9Fetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/session"))
      return response({ authenticated: true, user: me });
    if (url.endsWith("/api/v1/me")) return response(me);
    if (url.endsWith("/api/v1/auth/csrf"))
      return response({ csrf_token: "csrf" });
    if (url.endsWith("/api/v1/realtime/tickets"))
      return response({ ticket: "notification-ticket", expires_in: 30 });
    if (url.endsWith("/api/v1/notifications/unread-count"))
      return response({ unread_count: 3 });
    if (url.includes("/api/v1/notifications?"))
      return response({
        next: null,
        previous: null,
        results: [
          {
            id: "10000000-0000-4000-8000-000000000001",
            notification_type: "NEW_MESSAGE",
            actor: { id: 2, full_name: "Дмитрий Орлов" },
            source_type: "MESSAGE",
            source_id: "20000000-0000-4000-8000-000000000001",
            publication_id: null,
            conversation_id: "30000000-0000-4000-8000-000000000001",
            occurrence_count: 3,
            event_version: 3,
            created_at: "2026-08-25T09:00:00Z",
            last_event_at: "2026-08-25T09:02:00Z",
            read_at: null,
            target_url:
              "/messages?conversation=30000000-0000-4000-8000-000000000001&message=20000000-0000-4000-8000-000000000001",
          },
        ],
      });
    if (url.includes("/api/v1/notifications/") && url.endsWith("/read"))
      return response(null, 204);
    if (url.endsWith("/api/v1/notifications/read-all"))
      return response({ updated: 1 });
    if (url.endsWith("/api/v1/notification-settings")) {
      if (method === "PATCH") {
        const body = JSON.parse(String(init?.body)) as {
          enabled?: boolean;
          preferences?: NotificationPreference[];
        };
        return response({
          enabled: body.enabled ?? true,
          preferences: body.preferences ?? [preference],
        });
      }
      return response({ enabled: true, preferences: [preference] });
    }
    if (url.endsWith("/api/v1/push/config"))
      return response({ enabled: false, vapid_public_key: "" });
    if (url.includes("/api/v1/search?"))
      return response({
        publications: [
          {
            id: "publication",
            title: "Запуск продукта",
            snippet: "Новостями поделилась команда",
            url: "/news/publication",
          },
        ],
        comments: [
          {
            id: "comment",
            title: "Комментарий к публикации",
            snippet: "адамға арналған",
            url: "/news/publication?comment=comment",
          },
        ],
        messages: [
          {
            id: "message",
            title: "Командный чат",
            snippet: "Точное сообщение",
            url: "/messages?conversation=conversation&message=message",
          },
        ],
        files: [
          {
            id: "file",
            title: "release.pdf",
            snippet: "",
            url: "/api/v1/news/publication/media/file/download",
          },
        ],
        employees: [
          {
            id: 2,
            title: "Дмитрий Орлов",
            snippet: "Разработчик",
            url: "/employees?employee=2",
          },
        ],
      });
    return response({});
  });
}

beforeEach(() => {
  window.history.pushState({}, "", "/notifications");
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

test("renders grouped notifications and preserves the exact message target", async () => {
  const fetchMock = stage9Fetch();
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);

  expect(await screen.findByText("Дмитрий Орлов")).toBeVisible();
  expect(screen.getByText("Событий: 3")).toBeVisible();
  expect(screen.getByLabelText("Непрочитанных уведомлений: 3")).toBeVisible();
  expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    "/messages?conversation=30000000-0000-4000-8000-000000000001&message=20000000-0000-4000-8000-000000000001",
  );
  await userEvent.click(screen.getByRole("button", { name: "Прочитать все" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/notifications/read-all",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect((await axe(container)).violations).toHaveLength(0);
});

test("updates notification preferences and keeps push disabled by policy", async () => {
  window.history.pushState({}, "", "/settings/notifications");
  const fetchMock = stage9Fetch();
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Настройки уведомлений" }),
  ).toBeVisible();
  expect(
    screen.getByText(
      "Browser Push настроен, но отключён политикой безопасности.",
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Включить Browser Push" }),
  ).toBeDisabled();
  const checkboxes = screen.getAllByRole("checkbox");
  await userEvent.click(checkboxes[1]);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/notification-settings",
      expect.objectContaining({
        method: "PATCH",
        body: expect.stringContaining('"in_app_enabled":false'),
      }),
    ),
  );
});

test("renders all five search sections with authorization-safe exact links", async () => {
  window.history.pushState({}, "", "/search?q=новостями");
  vi.stubGlobal("fetch", stage9Fetch());
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Публикации" }),
  ).toBeVisible();
  for (const heading of ["Комментарии", "Сообщения", "Файлы", "Сотрудники"]) {
    expect(screen.getByRole("heading", { name: heading })).toBeVisible();
  }
  expect(screen.getByRole("link", { name: /Командный чат/ })).toHaveAttribute(
    "href",
    "/messages?conversation=conversation&message=message",
  );
  expect(screen.getByText("адамға арналған")).toBeVisible();
  expect((await axe(container)).violations).toHaveLength(0);
});
