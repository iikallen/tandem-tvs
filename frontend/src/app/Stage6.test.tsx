import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { api } from "../shared/api";
import { App } from "./App";

const member = {
  id: 1,
  username: "member",
  portal_id: null,
  full_name: "Локальный сотрудник",
  email: "member@example.invalid",
  job_title: "Сотрудник",
  phone: "",
  avatar_url: "",
  org_unit: null,
  module_roles: ["employee"],
  is_active: true,
  activated_at: "2026-08-24T08:00:00Z",
  access: { platform: [], news: ["MEMBER"], messenger: ["MEMBER"] },
};

const admin = {
  ...member,
  id: 2,
  username: "admin",
  full_name: "Администратор",
  access: {
    platform: ["ADMIN"],
    news: ["ADMIN"],
    messenger: ["ADMIN"],
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

beforeEach(() => {
  window.history.pushState({}, "", "/login");
  vi.restoreAllMocks();
});

test("logs in with the CSRF header and password-manager-compatible fields", async () => {
  let loginInit: RequestInit | undefined;
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/csrf"))
        return response({ csrf_token: "masked-csrf" });
      if (url.endsWith("/api/v1/auth/session"))
        return response({ authenticated: false, user: null });
      if (url.endsWith("/api/v1/auth/login")) {
        loginInit = init;
        return response({ user: member, csrf_token: "rotated-csrf" });
      }
      if (url.endsWith("/api/v1/me")) return response(member);
      if (
        url.endsWith("/api/v1/news/categories") ||
        url.endsWith("/api/v1/news/pinned")
      )
        return response([]);
      if (url.endsWith("/api/v1/news"))
        return response({ next: null, previous: null, results: [] });
      return response({});
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  await api.csrf();
  const { container } = render(<App />);

  const username = await screen.findByLabelText("Логин");
  const password = screen.getByLabelText("Пароль");
  expect(username).toHaveAttribute("autocomplete", "username");
  expect(password).toHaveAttribute("autocomplete", "current-password");
  await userEvent.type(username, "member");
  await userEvent.type(password, "a long local passphrase for tandem");
  await userEvent.click(screen.getByRole("button", { name: "Войти" }));

  await waitFor(() => expect(loginInit).toBeDefined());
  expect(loginInit?.credentials).toBe("same-origin");
  expect(loginInit?.headers).toMatchObject({ "X-CSRFToken": "masked-csrf" });
  expect(JSON.parse(String(loginInit?.body))).toEqual({
    username: "member",
    password: "a long local passphrase for tandem",
  });
  expect(
    await screen.findByRole("heading", { name: "Новости", level: 1 }),
  ).toBeVisible();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("activates an account with matching long passwords and the URL token", async () => {
  window.history.pushState({}, "", "/activate?token=one-time-token");
  let activationBody = "";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/csrf"))
        return response({ csrf_token: "masked-csrf" });
      if (url.endsWith("/api/v1/auth/session"))
        return response({ authenticated: false, user: null });
      if (url.endsWith("/api/v1/auth/activate")) {
        activationBody = String(init?.body);
        return response({ status: "activated" });
      }
      return response({});
    }),
  );
  await api.csrf();
  render(<App />);

  const next = await screen.findByLabelText("Новый пароль");
  const confirm = screen.getByLabelText("Повторите пароль");
  expect(next).toHaveAttribute("minlength", "15");
  expect(next).toHaveAttribute("maxlength", "128");
  await userEvent.type(next, "a long local passphrase for tandem");
  await userEvent.type(confirm, "a long local passphrase for tandem");
  await userEvent.click(
    screen.getByRole("button", { name: "Активировать аккаунт" }),
  );

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Пароль сохранён.",
  );
  expect(JSON.parse(activationBody).token).toBe("one-time-token");
});

test("platform admin creates one shared News and Messenger account", async () => {
  window.history.pushState({}, "", "/platform/users");
  const created = {
    ...member,
    id: 3,
    username: "new.user",
    full_name: "Новый пользователь",
  };
  let createBody = "";
  let accessRequest = "";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/csrf"))
        return response({ csrf_token: "masked-csrf" });
      if (url.endsWith("/api/v1/auth/session"))
        return response({ authenticated: true, user: admin });
      if (url.endsWith("/api/v1/me")) return response(admin);
      if (url.endsWith("/api/v1/platform/users") && init?.method === "POST") {
        createBody = String(init.body);
        return response(created, 201);
      }
      if (url.endsWith("/api/v1/platform/users/3/invitation"))
        return response({ activation_url: "/activate?token=invite" });
      if (url.endsWith("/api/v1/platform/users/2/grants/NEWS/MEMBER")) {
        accessRequest = init?.method ?? "";
        return response(null, 204);
      }
      if (url.includes("/api/v1/platform/users")) return response([admin]);
      return response({});
    }),
  );
  await api.csrf();
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Пользователи и доступ" }),
  ).toBeVisible();
  await userEvent.type(screen.getByLabelText("Логин"), "new.user");
  await userEvent.type(screen.getByLabelText("ФИО"), "Новый пользователь");
  await userEvent.type(
    screen.getByLabelText("Электронная почта"),
    "new@example.invalid",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Создать пользователя" }),
  );

  expect(await screen.findByLabelText("Одноразовая ссылка")).toHaveValue(
    "http://localhost:3000/activate?token=invite",
  );
  expect(JSON.parse(createBody).grants).toEqual([
    { module: "NEWS", role: "MEMBER" },
    { module: "MESSENGER", role: "MEMBER" },
  ]);
  await userEvent.click(screen.getByText("Изменить роли"));
  await userEvent.click(
    screen.getByRole("button", { name: "NEWS MEMBER · Назначить" }),
  );
  await waitFor(() => expect(accessRequest).toBe("PUT"));
  expect((await axe(container)).violations).toHaveLength(0);
});
