import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import type {
  Me,
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
}) {
  let sendAttempt = 0;
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/session"))
      return response({ authenticated: true, user: me });
    if (url.endsWith("/api/v1/me")) return response(me);
    if (url.endsWith("/api/v1/auth/csrf"))
      return response({ csrf_token: "csrf" });
    if (url.endsWith("/api/v1/realtime/tickets"))
      return response({ ticket: "one-time", expires_in: 30 });
    if (url.includes("/api/v1/messenger/people"))
      return response(options.people ?? []);
    if (url.endsWith("/api/v1/messenger/conversations"))
      return response(options.conversations ?? [conversation]);
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
      url.endsWith("/messages") &&
      method === "POST"
    ) {
      sendAttempt += 1;
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return options.send?.(body, sendAttempt) ?? response(savedMessage, 201);
    }
    if (
      url.includes("/api/v1/messenger/conversations/") &&
      url.includes("/messages")
    )
      return response({
        messages: [savedMessage],
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
    author: conversation.members[0].user,
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
              conversation.members[0],
              { ...conversation.members[1], user: charlie },
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
