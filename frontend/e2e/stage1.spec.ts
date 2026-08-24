import { expect, test } from "@playwright/test";

import { authenticatePage } from "./auth";

test.beforeEach(async ({ page }) => {
  await authenticatePage(page);
});

test("loads the portal projection and navigates to an employee search result", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Здравствуйте, Алия" }),
  ).toBeVisible();
  await expect(page.getByText("Локальная сессия защищена")).toBeVisible();

  await page
    .getByRole("navigation", { name: "Основная навигация" })
    .getByRole("link", { name: "Сотрудники" })
    .click();
  await page.getByRole("searchbox").fill("Орлов");

  await expect(
    page.getByRole("heading", { name: "Дмитрий Орлов" }),
  ).toBeVisible();
  await expect(page.getByText("Найдено: 1")).toBeVisible();
});

for (const width of [360, 390, 768, 1440]) {
  test(`${width}px viewport has the expected navigation and no horizontal overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");

    const mobileNavigation = page.getByRole("navigation", {
      name: "Мобильная навигация",
    });
    const desktopNavigation = page.getByRole("navigation", {
      name: "Основная навигация",
    });

    if (width < 768) {
      await expect(mobileNavigation).toBeVisible();
      await expect(desktopNavigation).toBeHidden();
    } else {
      await expect(mobileNavigation).toBeHidden();
      await expect(desktopNavigation).toBeVisible();
    }

    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  });
}

test("supports theme switching", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "Включить тёмную тему" }).click();
  await expect(page.locator(".app-shell")).toHaveAttribute(
    "data-theme",
    "dark",
  );
});

test("does not expose registration or token authentication APIs", async ({
  request,
}) => {
  for (const path of ["/api/v1/auth/register", "/api/token"]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(404);
  }
  expect((await request.get("/api/v1/auth/session")).status()).toBe(200);
});

test("renders the login screen when the local session is unavailable", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: false, user: null }),
    }),
  );

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Войти" })).toBeVisible();
});
