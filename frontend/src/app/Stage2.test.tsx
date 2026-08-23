import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

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
const editor = {
  ...employee,
  portal_id: "editor-1",
  module_roles: ["employee", "editor"],
};
const category = { id: 1, slug: "company", name: "Компания", sort_order: 0 };
const publication = {
  id: "b7a9e052-b4e6-4f58-8bbf-fc64257261e9",
  slug: "reglament-vpn",
  title: "Регламент VPN",
  summary: "Правила безопасного подключения",
  category,
  author: {
    portal_id: "editor-1",
    full_name: "Дмитрий Орлов",
    job_title: "Редактор",
  },
  published_at: "2026-08-23T09:00:00Z",
  cover: null,
  view_count: 2,
  comment_count: 0,
  reaction_count: 0,
  is_read: false,
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

test("renders, filters, and infinitely loads the addressed news feed", async () => {
  window.history.pushState({}, "", "/news");
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/v1/me")) return response(employee);
    if (url.includes("/api/v1/news/categories")) return response([category]);
    if (url.includes("cursor=next"))
      return response({
        next: null,
        previous: null,
        results: [{ ...publication, id: "second", title: "Вторая новость" }],
      });
    return response({
      next: "http://localhost/api/v1/news?cursor=next",
      previous: null,
      results: [publication],
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(<App />);

  expect(await screen.findByText("Регламент VPN")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Непрочитанные" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("unread=true"),
      expect.anything(),
    ),
  );
  await userEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
  expect(await screen.findByText("Вторая новость")).toBeVisible();
  expect((await axe(container)).violations).toHaveLength(0);
});

test("renders publication JSON safely without executable markup", async () => {
  window.history.pushState({}, "", `/news/${publication.id}`);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("/api/v1/me")
        ? response(employee)
        : response({
            ...publication,
            body: {
              type: "doc",
              content: [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: "Безопасный текст" }],
                },
                {
                  type: "script",
                  content: [{ type: "text", text: "не показывать" }],
                },
              ],
            },
          }),
    ),
  );
  render(<App />);

  expect(await screen.findByText("Безопасный текст")).toBeVisible();
  expect(screen.queryByText("не показывать")).not.toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
});

test("hides editorial navigation and route from an employee", async () => {
  window.history.pushState({}, "", "/editorial/publications");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response(employee)),
  );
  render(<App />);

  expect(await screen.findByRole("alert")).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Редакция" }),
  ).not.toBeInTheDocument();
});

test("editor creates and publishes through the role-gated workspace", async () => {
  window.history.pushState({}, "", "/editorial/publications/new");
  const editorialRecord = {
    ...publication,
    category: "company",
    body: {
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "VPN" }] },
      ],
    },
    status: "DRAFT",
    published_at: null,
    audience: {
      everyone: true,
      org_units: [],
      employees: [],
      module_roles: [],
    },
    created_at: "2026-08-23T09:00:00Z",
    updated_at: "2026-08-23T09:00:00Z",
  };
  const calls: Array<{ url: string; method: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (url.includes("/api/v1/me")) return response(editor);
      if (url.includes("/api/v1/news/categories")) return response([category]);
      if (url.includes("/api/v1/organization/units")) return response([]);
      if (url.endsWith("/publish"))
        return response({ ...editorialRecord, status: "PUBLISHED" });
      if (url.endsWith("/api/v1/editorial/publications") && method === "POST")
        return response(editorialRecord, 201);
      if (url.endsWith("/api/v1/editorial/publications"))
        return response({
          next: null,
          previous: null,
          results: [{ ...editorialRecord, status: "PUBLISHED" }],
        });
      return response({});
    }),
  );
  render(<App />);

  await userEvent.type(
    await screen.findByLabelText("Заголовок"),
    "Регламент VPN",
  );
  await userEvent.type(
    screen.getByLabelText("Краткое описание"),
    "Правила подключения",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "Текст публикации" }),
    "VPN безопасно",
  );
  await userEvent.click(screen.getByRole("button", { name: "Опубликовать" }));

  expect(
    await screen.findByRole("heading", { name: "Публикации" }),
  ).toBeVisible();
  expect(calls).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        method: "POST",
        url: "/api/v1/editorial/publications",
      }),
      expect.objectContaining({
        method: "POST",
        url: expect.stringMatching(/\/publish$/),
      }),
    ]),
  );
});
