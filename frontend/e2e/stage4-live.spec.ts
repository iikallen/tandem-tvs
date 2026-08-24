import { expect, test, type APIRequestContext } from "@playwright/test";

import { authenticateContext, authenticatedContext } from "./auth";

test.describe.configure({ mode: "serial" });

const body = (text: string) => ({
  type: "doc",
  content: [{ type: "paragraph", content: [{ type: "text", text }] }],
});

async function createDraft(request: APIRequestContext, suffix: string) {
  const response = await request.post("/api/v1/editorial/publications", {
    data: {
      title: `Stage 4 live ${suffix}`,
      summary: "Playwright acceptance",
      body: body("Живой редакционный сценарий"),
      category: "regulations",
      audience: {
        everyone: false,
        org_units: [],
        org_unit_subtrees: ["communications"],
        employees: [],
        module_roles: [],
        position_groups: [],
      },
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test("author autosaves and editor publishes the review", async ({
  browser,
}) => {
  const suffix = Date.now().toString();
  const author = await authenticatedContext(browser, "author-1");
  const authorPage = await author.newPage();
  const draft = await createDraft(author.request, suffix);
  await authorPage.goto(`/editorial/publications/${draft.id}`);
  const revisedTitle = `Автосохранено ${suffix}`;
  await authorPage.getByLabel("Заголовок").fill(revisedTitle);
  await expect(authorPage.getByRole("status")).toContainText("Автосохранено", {
    timeout: 8_000,
  });
  await authorPage.reload();
  await expect(authorPage.getByLabel("Заголовок")).toHaveValue(revisedTitle);
  await authorPage.getByRole("button", { name: "На согласование" }).click();
  await expect(authorPage).toHaveURL(/\/editorial\/publications$/);

  const editor = await authenticatedContext(browser, "editor-1");
  const editorPage = await editor.newPage();
  await editorPage.goto("/editorial/review");
  await expect(editorPage.getByText(revisedTitle)).toBeVisible();
  await editorPage.getByText(revisedTitle).click();
  await editorPage.getByRole("button", { name: "Опубликовать" }).click();
  await expect(editorPage).toHaveURL(/\/editorial\/publications$/);

  const addressed = await authenticatedContext(browser, "employee-1");
  const addressedPage = await addressed.newPage();
  await addressedPage.goto(`/news/${draft.id}`);
  await expect(addressedPage.getByText(revisedTitle)).toBeVisible();

  const outsider = await authenticatedContext(browser, "admin-1");
  const outsiderPage = await outsider.newPage();
  await outsiderPage.goto(`/news/${draft.id}`);
  await expect(outsiderPage.getByRole("alert")).toBeVisible();

  await Promise.all([
    author.close(),
    editor.close(),
    addressed.close(),
    outsider.close(),
  ]);
});

test("protected media survives HTTP delivery and Stage 4 layouts do not overflow", async ({
  browser,
}) => {
  const editor = await authenticatedContext(browser, "editor-1");
  const upload = await editor.request.post("/api/v1/editorial/media", {
    multipart: {
      file: {
        name: "stage4-playwright.png",
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
          "base64",
        ),
      },
    },
  });
  expect(upload.status()).toBe(201);
  const asset = await upload.json();
  expect((await editor.request.get(asset.content_url)).status()).toBe(200);

  const outsider = await authenticatedContext(browser, "employee-1");
  expect((await outsider.request.get(asset.content_url)).status()).toBe(404);
  await outsider.close();
  await editor.close();

  for (const width of [360, 390, 768, 1440]) {
    const context = await browser.newContext({
      viewport: { width, height: 900 },
    });
    await authenticateContext(context, "editor-1");
    const page = await context.newPage();
    await page.goto("/editorial/publications/new");
    await expect(
      page.getByRole("heading", { name: "Новая публикация" }),
    ).toBeVisible();
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
