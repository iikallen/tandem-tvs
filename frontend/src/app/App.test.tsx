import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

const profile = {
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
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
});

test("renders the portal shell and profile summary without accessibility violations", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response(profile)),
  );
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Здравствуйте, Алия" }),
  ).toBeVisible();
  expect(screen.getByText("SSO подключён")).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Основная навигация" }),
  ).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Мобильная навигация" }),
  ).toBeInTheDocument();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("shows a stable blocked account state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      response(
        { error: { code: "portal_account_blocked", message: "blocked" } },
        403,
      ),
    ),
  );
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Доступ заблокирован" }),
  ).toBeVisible();
  expect(screen.getByRole("alert")).toBeVisible();
});

test("shows a loading state while portal data is pending", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise<Response>(() => undefined)),
  );
  render(<App />);

  expect(screen.getByRole("status")).toHaveTextContent(
    "Загружаем данные портала",
  );
});

test("shows an unauthorized state when the portal session is missing", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ error: { code: "not_authenticated" } }, 401)),
  );
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Сессия портала не найдена" }),
  ).toBeVisible();
});

test("shows a portal unavailable state for dependency failures", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      response(
        { error: { code: "portal_unavailable", message: "unavailable" } },
        503,
      ),
    ),
  );
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Портал временно недоступен" }),
  ).toBeVisible();
});

test("shows the empty organization fallback", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ ...profile, org_unit: null })),
  );
  render(<App />);

  expect(await screen.findByText("Подразделение не назначено")).toBeVisible();
});

test("shows a generic API error state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ error: { code: "api_error" } }, 500)),
  );
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Не удалось загрузить данные" }),
  ).toBeVisible();
});

test("renders the read-only profile page", async () => {
  window.history.pushState({}, "", "/profile");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response(profile)),
  );
  const { container } = render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Алия Байжанова" }),
  ).toBeVisible();
  expect(screen.getByText("employee-1")).toBeVisible();
  expect(
    screen.queryByRole("textbox", { name: "ФИО" }),
  ).not.toBeInTheDocument();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("debounces employee search and renders results", async () => {
  window.history.pushState({}, "", "/employees");
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    return url.includes("%D0%9E%D1%80%D0%BB%D0%BE%D0%B2")
      ? response([
          {
            portal_id: "editor-1",
            full_name: "Дмитрий Орлов",
            email: "d.orlov@tandem.example",
            job_title: "Редактор",
            phone: "",
            avatar_url: "",
            org_unit_external_id: "communications",
            roles: ["employee", "editor"],
          },
        ])
      : response([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);

  const search = screen.getByRole("searchbox");
  await userEvent.type(search, "Орлов");
  expect(await screen.findByText("Дмитрий Орлов")).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect((await axe(container)).violations).toHaveLength(0);
});
