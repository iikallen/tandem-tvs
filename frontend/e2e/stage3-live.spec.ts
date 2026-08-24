import { expect, test } from "@playwright/test";

import { authenticateContext, authenticatedContext } from "./auth";

const publicationId = "00000000-0000-0000-0000-000000003001";

test.describe.configure({ mode: "serial" });

test("two addressed employees reconcile comments and reactions in realtime", async ({
  browser,
}) => {
  const commentBody = `Комментарий из настоящего браузера ${Date.now()}`;
  const contextA = await authenticatedContext(browser, "employee-1");
  const contextB = await authenticatedContext(browser, "author-1");
  await contextA.request.delete(`/api/v1/news/${publicationId}/reactions/LIKE`);
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

  await pageA.getByLabel("Комментарий").fill(commentBody);
  await pageA.getByRole("button", { name: "Отправить" }).click();
  await expect(pageB.getByText(commentBody)).toBeVisible({ timeout: 5_000 });

  await pageA.getByRole("button", { name: /Нравится/ }).click();
  await expect(pageB.getByRole("button", { name: /Нравится: 1/ })).toBeVisible({
    timeout: 5_000,
  });
  await pageB.reload();
  await expect(pageB.getByText(commentBody)).toBeVisible();
  await expect(
    pageB.getByRole("button", { name: /Нравится: 1/ }),
  ).toBeVisible();

  await contextA.close();
  await contextB.close();
});

test("outside employee receives not found and layouts do not overflow", async ({
  browser,
}) => {
  const outside = await authenticatedContext(browser, "admin-1");
  const outsidePage = await outside.newPage();
  await outsidePage.goto(`/news/${publicationId}`);
  await expect(outsidePage.getByRole("alert")).toBeVisible();
  await outside.close();

  for (const width of [360, 390, 768, 1440]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
    });
    await authenticateContext(context, "employee-1");
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
