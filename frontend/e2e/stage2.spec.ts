import { expect, type Page, test } from "@playwright/test";

const employee = {
  id: 4,
  username: "admin-1",
  portal_id: "admin-1",
  full_name: "Нурлан Касымов",
  email: "n@example.invalid",
  job_title: "Администратор",
  phone: "",
  avatar_url: "",
  org_unit: {
    external_id: "engineering",
    name: "Разработка",
    kind: "department",
    parent_external_id: "company",
  },
  module_roles: ["employee", "admin"],
  is_active: true,
  activated_at: "2026-08-23T08:00:00Z",
  access: {
    platform: ["ADMIN"],
    news: ["MEMBER", "ADMIN"],
    messenger: ["MEMBER"],
  },
};
const publication = {
  id: "b7a9e052-b4e6-4f58-8bbf-fc64257261e9",
  slug: "reglament-vpn",
  title: "Регламент VPN",
  summary: "Правила безопасного подключения",
  category: { id: 1, slug: "regulations", name: "Регламенты", sort_order: 10 },
  author: {
    portal_id: "editor-1",
    full_name: "Дмитрий Орлов",
    job_title: "Редактор",
  },
  published_at: "2026-08-23T09:00:00Z",
  cover: null,
  view_count: 0,
  comment_count: 0,
  reaction_count: 0,
  is_read: false,
};

async function mockProfile(page: Page, profile = employee) {
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: true, user: profile }),
    }),
  );
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(profile),
    }),
  );
}

test("editor creates and publishes Регламент VPN", async ({ page }) => {
  await mockProfile(page, {
    ...employee,
    id: 3,
    username: "editor-1",
    portal_id: "editor-1",
    full_name: "Дмитрий Орлов",
    module_roles: ["employee", "editor"],
    access: {
      platform: [],
      news: ["MEMBER", "EDITOR"],
      messenger: ["MEMBER"],
    },
  });
  await page.route("**/api/v1/news/categories", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([publication.category]),
    }),
  );
  await page.route("**/api/v1/organization/units", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          external_id: "engineering",
          name: "Разработка",
          kind: "department",
          parent_external_id: "company",
        },
      ]),
    }),
  );
  for (const path of [
    "**/api/v1/editorial/tags",
    "**/api/v1/editorial/media",
    "**/api/v1/organization/position-groups",
  ]) {
    await page.route(path, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      }),
    );
  }
  const editorial = {
    ...publication,
    category: "regulations",
    body: {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [{ type: "text", text: "VPN безопасно" }],
        },
      ],
    },
    status: "DRAFT",
    published_at: null,
    audience: {
      everyone: false,
      org_units: ["engineering"],
      employees: [],
      module_roles: [],
    },
    created_at: "2026-08-23T09:00:00Z",
    updated_at: "2026-08-23T09:00:00Z",
  };
  await page.route("**/api/v1/editorial/publications", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(editorial),
      });
    } else {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          next: null,
          previous: null,
          results: [{ ...editorial, status: "PUBLISHED" }],
        }),
      });
    }
  });
  await page.route("**/api/v1/editorial/publications/*/publish", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...editorial,
        status: "PUBLISHED",
        published_at: publication.published_at,
      }),
    }),
  );

  await page.goto("/editorial/publications/new");
  await page.getByLabel("Заголовок").fill("Регламент VPN");
  await page
    .getByLabel("Краткое описание")
    .fill("Правила безопасного подключения");
  await page
    .getByRole("textbox", { name: "Текст публикации" })
    .fill("VPN безопасно");
  await page.getByLabel("Аудитория").selectOption("ORG_UNIT");
  await page.getByLabel("Подразделения").selectOption("engineering");
  await page.getByRole("button", { name: "Опубликовать" }).click();

  await expect(page.getByRole("heading", { name: "Публикации" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Регламент VPN" }),
  ).toBeVisible();
});

test("addressed employee sees feed, detail, search and unread", async ({
  page,
}) => {
  await mockProfile(page);
  await page.route("**/api/v1/news/categories", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  for (const pattern of ["**/api/v1/news", "**/api/v1/news?*"]) {
    await page.route(pattern, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          next: null,
          previous: null,
          results: [publication],
        }),
      }),
    );
  }
  await page.route(`**/api/v1/news/${publication.id}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...publication,
        is_read: true,
        view_count: 1,
        body: {
          type: "doc",
          content: [
            {
              type: "paragraph",
              content: [{ type: "text", text: "VPN безопасно" }],
            },
          ],
        },
      }),
    }),
  );

  await page.goto("/news");
  await expect(page.getByText("Регламент VPN")).toBeVisible();
  await page.getByRole("button", { name: "Непрочитанные" }).click();
  await expect(page.getByText("Регламент VPN")).toBeVisible();
  await page.getByPlaceholder("Поиск по заголовку и тексту").fill("VPN");
  await expect(page.getByText("Регламент VPN")).toBeVisible();
  await page.getByText("Регламент VPN").click();
  await expect(page.getByText("VPN безопасно")).toBeVisible();
});

test("outside employee sees no row and direct URL is not found", async ({
  page,
}) => {
  await mockProfile(page, {
    ...employee,
    portal_id: "employee-1",
    full_name: "Алия Байжанова",
    module_roles: ["employee"],
  });
  await page.route("**/api/v1/news/categories", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/v1/news", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ next: null, previous: null, results: [] }),
    }),
  );
  await page.route(`**/api/v1/news/${publication.id}`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "not_found", message: "Not found." },
      }),
    }),
  );

  await page.goto("/news");
  await expect(
    page.getByRole("heading", { name: "Новостей пока нет" }),
  ).toBeVisible();
  await page.goto(`/news/${publication.id}`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("Регламент VPN")).toHaveCount(0);
});

for (const width of [360, 390, 768, 1440]) {
  test(`news feed has no horizontal overflow at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockProfile(page);
    await page.route("**/api/v1/news/categories", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      }),
    );
    await page.route("**/api/v1/news", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          next: null,
          previous: null,
          results: [publication],
        }),
      }),
    );
    await page.goto("/news");
    await expect(page.getByText("Регламент VPN")).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  });
}
