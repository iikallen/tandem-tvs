import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import type {
  Me,
  MediaAsset,
  MessengerConversation,
  MessengerMessage,
  MessengerPerson,
} from "../shared/api";
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
  activated_at: "2026-08-24T08:00:00Z",
  access: { platform: [], news: ["MEMBER"], messenger: ["MEMBER"] },
};

const bob: MessengerPerson = {
  id: 2,
  username: "dmitry",
  full_name: "Дмитрий Орлов",
  job_title: "Service Desk",
  avatar_url: "",
  org_unit_name: "Поддержка",
};

const savedMessage: MessengerMessage = {
  id: "10000000-0000-4000-8000-000000000001",
  sequence: 1,
  client_message_id: "20000000-0000-4000-8000-000000000001",
  author: bob,
  body: "Проверка realtime",
  created_at: "2026-08-24T10:40:00Z",
  receipt: { read: false, read_count: 0, recipient_count: 1 },
};

const imageAsset: MediaAsset = {
  id: "60000000-0000-4000-8000-000000000001",
  original_name: "scheme.png",
  mime_type: "image/png",
  size: 2048,
  sha256: "a".repeat(64),
  kind: "IMAGE",
  width: 640,
  height: 480,
  status: "READY",
  created_at: savedMessage.created_at,
  content_url: "/media/scheme.png",
};

const videoAsset: MediaAsset = {
  ...imageAsset,
  id: "60000000-0000-4000-8000-000000000002",
  original_name: "demo.mp4",
  mime_type: "video/mp4",
  kind: "VIDEO",
  width: 1280,
  height: 720,
  content_url: "/media/demo.mp4",
};

const documentAsset: MediaAsset = {
  ...imageAsset,
  id: "60000000-0000-4000-8000-000000000003",
  original_name: "brief.pdf",
  mime_type: "application/pdf",
  kind: "DOCUMENT",
  width: null,
  height: null,
  content_url: "/media/brief.pdf",
};

const conversation: MessengerConversation = {
  id: "30000000-0000-4000-8000-000000000001",
  type: "DIRECT",
  title: "",
  created_by_id: bob.id,
  last_sequence: 1,
  last_message_at: savedMessage.created_at,
  created_at: savedMessage.created_at,
  unread_count: 1,
  last_message: savedMessage,
  members: [
    {
      user: {
        id: me.id,
        username: me.username,
        full_name: me.full_name,
        job_title: me.job_title,
        avatar_url: me.avatar_url,
        org_unit_name: null,
      },
      role: "MEMBER",
      joined_at: savedMessage.created_at,
      last_read_sequence: 0,
      read_at: null,
    },
    {
      user: bob,
      role: "MEMBER",
      joined_at: savedMessage.created_at,
      last_read_sequence: 1,
      read_at: savedMessage.created_at,
    },
  ],
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
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {}
}

function baseFetch(options: {
  send?: (body: Record<string, unknown>, attempt: number) => Response;
  people?: MessengerPerson[];
  conversations?: MessengerConversation[];
  messages?: MessengerMessage[];
  user?: Me;
}) {
  let sendAttempt = 0;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/session"))
      return response({ authenticated: true, user: options.user ?? me });
    if (url.endsWith("/api/v1/me")) return response(options.user ?? me);
    if (url.endsWith("/api/v1/auth/csrf"))
      return response({ csrf_token: "csrf" });
    if (url.endsWith("/api/v1/realtime/tickets"))
      return response({ ticket: "one-time", expires_in: 30 });
    if (url.includes("/api/v1/messenger/people"))
      return response(options.people ?? []);
    if (url.endsWith("/api/v1/messenger/conversations"))
      return response({
        results: options.conversations ?? [conversation],
        next: null,
      });
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.includes("/members?")
    )
      return response({ results: conversation.members ?? [], next: null });
    if (url.endsWith(`/api/v1/messenger/conversations/${conversation.id}`))
      return response(conversation);
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.endsWith("/read")
    )
      return response({
        last_read_sequence: 1,
        read_at: savedMessage.created_at,
      });
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.includes("/search?")
    )
      return response({ results: options.messages ?? [savedMessage] });
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.endsWith("/messages") &&
      method === "POST"
    ) {
      sendAttempt += 1;
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return options.send?.(body, sendAttempt) ?? response(savedMessage, 201);
    }
    if (url.endsWith(`/api/v1/messenger/messages/${savedMessage.id}`))
      return response(savedMessage);
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.includes("/messages")
    )
      return response({
        messages: options.messages ?? [savedMessage],
        has_more: false,
        next_before_sequence: null,
      });
    return response({});
  });
}

beforeEach(() => {
  window.history.pushState({}, "", "/messages");
  FakeWebSocket.instances = [];
  vi.restoreAllMocks();
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

test("shows inbox, opens a direct thread, marks it read, and sends with a client UUID", async () => {
  let sent: Record<string, unknown> | undefined;
  const outgoing = {
    ...savedMessage,
    id: "10000000-0000-4000-8000-000000000002",
    sequence: 2,
    author: conversation.members![0].user,
    body: "Релиз готов",
    receipt: { read: false, read_count: 0, recipient_count: 1 },
  };
  vi.stubGlobal(
    "fetch",
    baseFetch({
      send: (body) => {
        sent = body;
        return response(
          { ...outgoing, client_message_id: body.client_message_id },
          201,
        );
      },
    }),
  );
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Сообщения" }),
  ).toBeVisible();
  expect(
    screen.getByText("1", { selector: ".messenger-unread" }),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /Дмитрий Орлов/ }));
  expect(
    await screen.findByText("Проверка realtime", {
      selector: ".messenger-message p",
    }),
  ).toBeVisible();
  await userEvent.type(screen.getByLabelText("Сообщение"), "Релиз готов");
  await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

  await waitFor(() => expect(sent).toBeDefined());
  expect(sent?.body).toBe("Релиз готов");
  expect(sent?.client_message_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(await screen.findByText("Релиз готов")).toBeVisible();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("retries an uncertain send with the same client_message_id", async () => {
  const ids: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    baseFetch({
      send: (body, attempt) => {
        ids.push(body.client_message_id);
        return attempt === 1
          ? response({ error: { code: "api_error", message: "offline" } }, 503)
          : response(
              { ...savedMessage, client_message_id: body.client_message_id },
              200,
            );
      },
    }),
  );
  render(<App />);

  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );
  await userEvent.type(screen.getByLabelText("Сообщение"), "Один раз");
  await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Повторить" }),
  );

  await waitFor(() => expect(ids).toHaveLength(2));
  expect(ids[0]).toBe(ids[1]);
});

test("creates direct and group conversations from the local Messenger directory", async () => {
  const charlie: MessengerPerson = {
    ...bob,
    id: 3,
    username: "charlie",
    full_name: "Чарли Сеитов",
  };
  const created: Array<Record<string, unknown>> = [];
  const fetchMock = baseFetch({ conversations: [], people: [charlie] });
  fetchMock.mockImplementation(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/conversations/direct")) {
        created.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return response(
          {
            ...conversation,
            id: "direct-created",
            members: [
              conversation.members![0],
              { ...conversation.members![1], user: charlie },
            ],
          },
          201,
        );
      }
      if (url.endsWith("/conversations/group")) {
        created.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return response(
          {
            ...conversation,
            id: "group-created",
            type: "GROUP",
            title: "Команда",
          },
          201,
        );
      }
      return baseFetch({ conversations: [], people: [charlie] })(input, init);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);

  await userEvent.click(
    await screen.findByRole("button", { name: "Новое сообщение" }),
  );
  await userEvent.click(await screen.findByText("Написать"));
  await waitFor(() => expect(created[0]).toEqual({ user_id: charlie.id }));

  await userEvent.click(
    screen.getByRole("button", { name: "Назад к диалогам" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Новая группа" }));
  await userEvent.type(screen.getByLabelText("Название группы"), "Команда");
  await userEvent.click(await screen.findByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Создать группу" }));
  await waitFor(() =>
    expect(created[1]).toEqual({ title: "Команда", member_ids: [charlie.id] }),
  );
});

test("keeps keyboard focus in the new-conversation dialog and restores it on Escape", async () => {
  vi.stubGlobal("fetch", baseFetch({ conversations: [], people: [bob] }));
  render(<App />);
  const user = userEvent.setup();
  const openButton = await screen.findByRole("button", {
    name: "Новое сообщение",
  });
  await user.click(openButton);
  const search = screen.getByLabelText("Поиск сотрудника");
  expect(search).toHaveFocus();
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(screen.getByRole("button", { name: "Закрыть" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(openButton).toHaveFocus();
});

test("deduplicates outbox events and coalesces receipt bursts", async () => {
  const fetchMock = baseFetch({});
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );
  await waitFor(() =>
    expect(FakeWebSocket.instances[0]?.onmessage).not.toBeNull(),
  );
  const socket = FakeWebSocket.instances[0];
  const messageGets = () =>
    fetchMock.mock.calls.filter(([input, init]) => {
      const url = String(input);
      return (
        url.endsWith(`/conversations/${conversation.id}/messages`) &&
        (init?.method ?? "GET") === "GET"
      );
    }).length;
  const initial = messageGets();
  const detailGets = () =>
    fetchMock.mock.calls.filter(([input, init]) => {
      const url = String(input);
      return (
        url.endsWith(`/api/v1/messenger/messages/${savedMessage.id}`) &&
        (init?.method ?? "GET") === "GET"
      );
    }).length;
  const initialDetails = detailGets();
  const duplicate = JSON.stringify({
    version: 2,
    event_id: "40000000-0000-4000-8000-000000000001",
    type: "messenger.message.created",
    conversation_id: conversation.id,
    message_id: savedMessage.id,
    sequence: 1,
  });
  socket.onmessage?.({ data: duplicate });
  await waitFor(() => expect(detailGets()).toBe(initialDetails + 1));
  expect(messageGets()).toBe(initial);
  socket.onmessage?.({ data: duplicate });
  await new Promise((resolve) => window.setTimeout(resolve, 50));
  expect(detailGets()).toBe(initialDetails + 1);

  const beforeReceipts = messageGets();
  for (let index = 0; index < 3; index += 1) {
    socket.onmessage?.({
      data: JSON.stringify({
        version: 2,
        event_id: `50000000-0000-4000-8000-00000000000${index}`,
        type: "messenger.delivered.changed",
        conversation_id: conversation.id,
        user_id: bob.id,
        sequence: 1,
      }),
    });
  }
  await waitFor(() => expect(messageGets()).toBe(beforeReceipts + 1), {
    timeout: 1_000,
  });
});

test("searches the inbox and prefills a shared News link after choosing a chat", async () => {
  window.history.pushState({}, "", "/messages?share=%2Fnews%2Freglament-vpn");
  vi.stubGlobal("fetch", baseFetch({}));
  render(<App />);

  const inboxSearch = await screen.findByLabelText(
    "Поиск по названию или участникам",
  );
  await userEvent.type(inboxSearch, "неизвестный");
  expect(
    screen.queryByRole("button", { name: /Дмитрий Орлов/ }),
  ).not.toBeInTheDocument();
  await userEvent.clear(inboxSearch);
  await userEvent.type(inboxSearch, "Дмитрий");
  await userEvent.click(screen.getByRole("button", { name: /Дмитрий Орлов/ }));

  expect(await screen.findByLabelText("Сообщение")).toHaveValue(
    "/news/reglament-vpn",
  );
});

test("filters messages by author, date, and attachments", async () => {
  const fetchMock = baseFetch({});
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );
  await userEvent.click(screen.getByText("Расширенные фильтры"));
  await userEvent.selectOptions(screen.getByLabelText("Автор"), String(bob.id));
  fireEvent.change(screen.getByLabelText("С даты"), {
    target: { value: "2026-08-01" },
  });
  fireEvent.change(screen.getByLabelText("По дату"), {
    target: { value: "2026-08-31" },
  });
  await userEvent.click(screen.getByLabelText("Только с вложениями"));

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([input]) => {
        const url = new URL(String(input), "http://localhost");
        return (
          url.pathname.endsWith(`/conversations/${conversation.id}/search`) &&
          url.searchParams.get("author_id") === String(bob.id) &&
          url.searchParams.has("date_from") &&
          url.searchParams.has("date_to") &&
          url.searchParams.get("has_attachments") === "true"
        );
      }),
    ).toBe(true),
  );
});

test("renders media previews, publication cards, and the authorized attachment tab", async () => {
  const message = {
    ...savedMessage,
    attachments: [imageAsset, videoAsset, documentAsset],
    resource_preview: {
      type: "publication" as const,
      id: "publication-id",
      title: "Регламент VPN",
      url: "/news/publication-id",
    },
  };
  const fetchMock = baseFetch({ messages: [message] });
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );

  expect(await screen.findByRole("img", { name: "scheme.png" })).toBeVisible();
  expect(screen.getByLabelText("demo.mp4")).toBeVisible();
  expect(screen.getByRole("link", { name: "Скачать файл" })).toHaveAttribute(
    "download",
    "brief.pdf",
  );
  expect(screen.getByRole("link", { name: /Регламент VPN/ })).toHaveAttribute(
    "href",
    "/news/publication-id",
  );

  await userEvent.click(screen.getByRole("tab", { name: "Файлы" }));
  expect(
    await screen.findByText("brief.pdf", {
      selector: ".messenger-attachment-list strong",
    }),
  ).toBeVisible();
  expect(
    fetchMock.mock.calls.some(([input]) =>
      String(input).includes("has_attachments=true"),
    ),
  ).toBe(true);
});

test("uploads pasted and dropped files and cancels an in-flight upload", async () => {
  const fallback = baseFetch({});
  let uploadCount = 0;
  const pendingSignal: { current: AbortSignal | null } = { current: null };
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      if (url.endsWith(`/conversations/${conversation.id}/attachments`)) {
        uploadCount += 1;
        if (uploadCount === 1) return response(documentAsset, 201);
        pendingSignal.current = init?.signal ?? null;
        return new Promise((_resolve, reject) => {
          pendingSignal.current?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        });
      }
      return fallback(input, init);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );
  const composer = document.querySelector(".messenger-composer");
  expect(composer).not.toBeNull();
  fireEvent.paste(composer!, {
    clipboardData: {
      files: [new File(["pdf"], "brief.pdf", { type: "application/pdf" })],
    },
  });
  expect(await screen.findByText("brief.pdf")).toBeVisible();

  fireEvent.drop(composer!, {
    dataTransfer: {
      files: [new File(["png"], "drop.png", { type: "image/png" })],
    },
  });
  await userEvent.click(
    await screen.findByRole("button", { name: "Отменить загрузку" }),
  );
  expect(pendingSignal.current?.aborted).toBe(true);
  await waitFor(() =>
    expect(
      screen.queryByRole("progressbar", { name: "Загрузка файла" }),
    ).not.toBeInTheDocument(),
  );
});

test("submits a complaint and lets a Messenger moderator resolve the queue", async () => {
  const moderator: Me = {
    ...me,
    access: { ...me.access, messenger: ["MEMBER", "MODERATOR"] },
  };
  const fallback = baseFetch({ user: moderator });
  const actions: Array<Record<string, unknown>> = [];
  const reportId = "70000000-0000-4000-8000-000000000001";
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith(`/messages/${savedMessage.id}/report`)) {
        actions.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return response({ id: reportId, state: "OPEN" }, 201);
      }
      if (url.endsWith(`/moderation/reports/${reportId}/resolve`)) {
        actions.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return response({ id: reportId, state: "RESOLVED" });
      }
      if (url.endsWith("/messenger/moderation/reports") && method === "GET")
        return response({
          reports: [
            {
              id: reportId,
              reason: "Нарушение правил",
              state: "OPEN",
              created_at: savedMessage.created_at,
              reporter_id: me.id,
              message: {
                id: savedMessage.id,
                conversation_id: conversation.id,
                author_id: bob.id,
                body: savedMessage.body,
                created_at: savedMessage.created_at,
              },
            },
          ],
        });
      return fallback(input, init);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Дмитрий Орлов/ }),
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Пожаловаться" }),
  );
  await userEvent.type(
    screen.getByLabelText("Причина жалобы"),
    "Нарушение правил",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Отправить жалобу" }),
  );
  await waitFor(() =>
    expect(actions[0]).toEqual({ reason: "Нарушение правил" }),
  );

  await userEvent.click(
    screen.getByRole("button", { name: "Модерация Messenger" }),
  );
  expect(await screen.findByText(/Нарушение правил/)).toBeVisible();
  await userEvent.type(
    screen.getByLabelText("Комментарий модератора"),
    "Проверено",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить нарушение" }),
  );
  await waitFor(() =>
    expect(actions[1]).toEqual({ decision: "VIOLATION", note: "Проверено" }),
  );
});
