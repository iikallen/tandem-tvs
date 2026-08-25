import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const admin = {
  id: 10,
  username: "news-admin",
  portal_id: "news-admin",
  full_name: "Администратор Новостей",
  email: "admin@example.invalid",
  job_title: "Администратор",
  phone: "",
  avatar_url: "",
  org_unit: null,
  module_roles: ["admin"],
  is_active: true,
  activated_at: "2026-08-25T08:00:00Z",
  access: { platform: [], news: ["ADMIN"], messenger: [] },
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
  close() {}
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

test("renders the admin audit trail as escaped state", async () => {
  window.history.pushState({}, "", "/editorial/audit");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session"))
        return response({ authenticated: true, user: admin });
      if (url.endsWith("/api/v1/me")) return response(admin);
      if (url.endsWith("/api/v1/notifications/unread-count"))
        return response({ unread_count: 0 });
      if (url.endsWith("/api/v1/auth/csrf"))
        return response({ csrf_token: "test" });
      if (url.endsWith("/api/v1/realtime/tickets"))
        return response({ ticket: "ticket", expires_in: 30 });
      return response({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 1,
            event_type: "publication.updated",
            target_type: "publication",
            target_id: "publication-1",
            actor: admin,
            previous_state: { title: "До" },
            new_state: { title: "<script>alert(1)</script>" },
            created_at: "2026-08-25T09:00:00Z",
          },
        ],
      });
    }),
  );

  const { container } = render(<App />);

  expect(await screen.findByText("publication.updated")).toBeVisible();
  expect(screen.getByText(/Исполнитель: Администратор Новостей/)).toBeVisible();
  expect(screen.getByText(/<script>alert\(1\)<\/script>/)).toBeVisible();
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByRole("link", { name: "Журнал аудита" })).toBeVisible();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("updates upload and retention policy through existing settings API", async () => {
  window.history.pushState({}, "", "/editorial/settings/engagement");
  let submitted: Record<string, unknown> | undefined;
  const settings = {
    comment_edit_window_minutes: 60,
    comment_delete_window_minutes: 60,
    enabled_reaction_types: ["LIKE"],
    max_comment_attachments: 5,
    max_comment_attachment_bytes: 26214400,
    allowed_media_extensions: [".png", ".pdf"],
    message_retention_days: 0,
    media_retention_days: 0,
    stop_words: [],
    updated_at: "2026-08-25T09:00:00Z",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session"))
        return response({ authenticated: true, user: admin });
      if (url.endsWith("/api/v1/me")) return response(admin);
      if (url.endsWith("/api/v1/notifications/unread-count"))
        return response({ unread_count: 0 });
      if (url.endsWith("/api/v1/auth/csrf"))
        return response({ csrf_token: "test" });
      if (url.endsWith("/api/v1/realtime/tickets"))
        return response({ ticket: "ticket", expires_in: 30 });
      if (
        url.endsWith("/api/v1/editorial/settings/engagement") &&
        init?.method === "PATCH"
      ) {
        submitted = JSON.parse(String(init.body)) as Record<string, unknown>;
        return response({ ...settings, ...submitted });
      }
      return response(settings);
    }),
  );

  render(<App />);
  const uploadLimit = await screen.findByRole("spinbutton", {
    name: "Лимит загрузки, байт",
  });
  await userEvent.clear(uploadLimit);
  await userEvent.type(uploadLimit, "1048576");
  const extensions = screen.getByRole("textbox", {
    name: "Разрешённые расширения через запятую",
  });
  fireEvent.change(extensions, { target: { value: ".jpg, .pdf" } });
  await userEvent.type(
    screen.getByRole("spinbutton", {
      name: "Хранение сообщений, дней (0 — бессрочно)",
    }),
    "30",
  );
  await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() => expect(submitted).toBeDefined());
  expect(submitted).toMatchObject({
    max_comment_attachment_bytes: 1048576,
    allowed_media_extensions: [".jpg", ".pdf"],
    message_retention_days: 30,
  });
});
