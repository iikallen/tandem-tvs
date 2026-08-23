import { expect, test } from "@playwright/test";

const publicationId = "00000000-0000-0000-0000-000000003001";

test.describe.configure({ mode: "serial" });

test("two addressed employees reconcile comments and reactions in realtime", async ({
  browser,
}) => {
  const contextA = await browser.newContext({
    extraHTTPHeaders: { "X-Mock-Portal-User": "employee-1" },
  });
  const contextB = await browser.newContext({
    extraHTTPHeaders: { "X-Mock-Portal-User": "author-1" },
  });
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();

  await Promise.all([
    pageA.goto(`/news/${publicationId}`),
    pageB.goto(`/news/${publicationId}`),
  ]);
  await expect(pageA.getByText("Живая публикация Stage 3")).toBeVisible();
  await expect(pageB.getByText("Живая публикация Stage 3")).toBeVisible();
  await expect(
    pageA.getByText("Обновления в реальном времени подключены"),
  ).toBeVisible();
  await expect(
    pageB.getByText("Обновления в реальном времени подключены"),
  ).toBeVisible();

  await pageA
    .getByLabel("Комментарий")
    .fill("Комментарий из настоящего браузера");
  await pageA.getByRole("button", { name: "Отправить" }).click();
  await expect(
    pageB.getByText("Комментарий из настоящего браузера"),
  ).toBeVisible({ timeout: 2_000 });

  await pageA.getByRole("button", { name: /Нравится/ }).click();
  await expect(pageB.getByRole("button", { name: /Нравится · 1/ })).toBeVisible(
    { timeout: 2_000 },
  );
  await pageB.reload();
  await expect(
    pageB.getByText("Комментарий из настоящего браузера"),
  ).toBeVisible();
  await expect(
    pageB.getByRole("button", { name: /Нравится · 1/ }),
  ).toBeVisible();

  await contextA.close();
  await contextB.close();
});

test("outside employee receives not found and layouts do not overflow", async ({
  browser,
}) => {
  const outside = await browser.newContext({
    extraHTTPHeaders: { "X-Mock-Portal-User": "admin-1" },
  });
  const outsidePage = await outside.newPage();
  await outsidePage.goto(`/news/${publicationId}`);
  await expect(outsidePage.getByRole("alert")).toBeVisible();
  await outside.close();

  for (const width of [360, 390, 768, 1440]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
      extraHTTPHeaders: { "X-Mock-Portal-User": "employee-1" },
    });
    const page = await context.newPage();
    await page.goto(`/news/${publicationId}`);
    await expect(page.getByText("Живая публикация Stage 3")).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    await context.close();
  }
});
