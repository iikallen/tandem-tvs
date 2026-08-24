import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const profile = {
  id: 1,
  username: "employee-1",
  portal_id: "employee-1",
  full_name: "Алия Байжанова",
  email: "a.baizhanova@tandem.example",
  job_title: "Специалист",
  phone: "+7 700 000 00 01",
  avatar_url: "",
  org_unit: {
    external_id: "communications",
    name: "Корпоративные коммуникации",
    kind: "department",
    parent_external_id: "company",
  },
  module_roles: ["employee"],
  is_active: true,
  activated_at: "2026-08-23T08:00:00Z",
  access: { platform: [], news: ["MEMBER"], messenger: ["MEMBER"] },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function authenticatedFetch(user: unknown = profile) {
  return vi.fn(async (input: RequestInfo | URL) =>
    String(input).includes("/api/v1/auth/session")
      ? response({ authenticated: true, user })
      : response(user),
  );
}

beforeEach(() => {
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
});

test("renders the authenticated shell without accessibility violations", async () => {
  vi.stubGlobal("fetch", authenticatedFetch());
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Здравствуйте, Алия" }),
  ).toBeVisible();
  expect(screen.getByText("Локальная сессия защищена")).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Основная навигация" }),
  ).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Мобильная навигация" }),
  ).toBeInTheDocument();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("redirects an anonymous visitor to the accessible login form", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ authenticated: false, user: null })),
  );
  const { container } = render(<App />);

  expect(await screen.findByRole("heading", { name: "Войти" })).toBeVisible();
  expect(screen.getByLabelText("Логин")).toHaveAttribute(
    "autocomplete",
    "username",
  );
  expect(screen.getByLabelText("Пароль")).toHaveAttribute(
    "autocomplete",
    "current-password",
  );
  expect((await axe(container)).violations).toHaveLength(0);
});

test("shows a loading state while the local session is pending", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => undefined)),
  );
  render(<App />);

  expect(screen.getByRole("status")).toBeVisible();
});

test("shows the empty organization fallback", async () => {
  const user = { ...profile, org_unit: null };
  vi.stubGlobal("fetch", authenticatedFetch(user));
  render(<App />);

  expect(await screen.findByText("Подразделение не назначено")).toBeVisible();
});

test("renders the read-only profile page", async () => {
  window.history.pushState({}, "", "/profile");
  vi.stubGlobal("fetch", authenticatedFetch());
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Алия Байжанова" }),
  ).toBeVisible();
  expect(screen.getAllByText("employee-1").length).toBeGreaterThan(0);
  expect(
    screen.queryByRole("textbox", { name: "ФИО" }),
  ).not.toBeInTheDocument();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("debounces employee search and renders portal directory results", async () => {
  window.history.pushState({}, "", "/employees");
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/auth/session"))
      return response({ authenticated: true, user: profile });
    if (url.includes("/api/v1/me")) return response(profile);
    return url.includes("%D0%9E%D1%80%D0%BB%D0%BE%D0%B2")
      ? response([
          {
            portal_id: "editor-1",
            full_name: "Дмитрий Орлов",
            job_title: "Редактор",
            org_unit_external_id: "communications",
          },
        ])
      : response([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);

  await userEvent.type(await screen.findByRole("searchbox"), "Орлов");
  expect(await screen.findByText("Дмитрий Орлов")).toBeVisible();
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("%D0%9E%D1%80%D0%BB%D0%BE%D0%B2"),
      expect.anything(),
    ),
  );
  expect((await axe(container)).violations).toHaveLength(0);
});
