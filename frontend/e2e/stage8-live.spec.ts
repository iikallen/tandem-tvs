import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { authenticatedContext } from "./auth";

test.describe.configure({ mode: "serial", timeout: 90_000 });

const groupTitle = "Stage 8 Acceptance Group";

async function openGroup(page: Page) {
  await page.goto("/messages");
  await expect(page.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени подключены",
  );
  await page.getByRole("button", { name: new RegExp(groupTitle) }).click();
  await expect(page.getByRole("heading", { name: groupTitle })).toBeVisible();
}

async function group(context: BrowserContext) {
  const response = await context.request.get("/api/v1/messenger/conversations");
  expect(response.status()).toBe(200);
  const payload = await response.json();
  return payload.results.find(
    (conversation: { title: string }) => conversation.title === groupTitle,
  );
}

function messageByBody(page: Page, body: string) {
  return page
    .locator(".messenger-message > p")
    .getByText(body, { exact: true })
    .locator("..");
}

test("two browsers complete reply, edit, reaction and tombstone flows", async ({
  browser,
}) => {
  const alice = await authenticatedContext(browser, "stage7-alice");
  const outsider = await authenticatedContext(browser, "stage7-outsider");
  const alicePage = await alice.newPage();
  const outsiderPage = await outsider.newPage();
  await Promise.all([openGroup(alicePage), openGroup(outsiderPage)]);

  const original = `Stage 8 browser message ${Date.now()}`;
  const reply = `Stage 8 browser reply ${Date.now()}`;
  await alicePage.getByLabel("Сообщение").fill(original);
  await alicePage.getByRole("button", { name: "Отправить" }).click();
  const outsiderMessage = outsiderPage
    .locator(".messenger-message")
    .filter({ hasText: original });
  await expect(outsiderMessage).toBeVisible();
  await outsiderMessage.getByRole("button", { name: "Ответить" }).click();
  await outsiderPage.getByLabel("Сообщение").fill(reply);
  await outsiderPage.getByRole("button", { name: "Отправить" }).click();
  await expect(
    alicePage.locator(".messenger-message").filter({
      hasText: reply,
    }),
  ).toContainText(original);

  const aliceMessage = alicePage
    .locator(".messenger-message")
    .filter({ hasText: original });
  await aliceMessage.getByRole("button", { name: "Изменить" }).click();
  await alicePage.getByLabel("Сообщение").fill(`${original} edited`);
  await alicePage.getByRole("button", { name: "Отправить" }).click();
  const updated = messageByBody(outsiderPage, `${original} edited`);
  await expect(updated).toContainText("изменено");
  await updated.getByRole("button", { name: /^LOVE/ }).click();
  await expect(
    messageByBody(alicePage, `${original} edited`).getByRole("button", {
      name: /LOVE 1/,
    }),
  ).toBeVisible();

  const tombstones = outsiderPage
    .locator(".messenger-message > p")
    .getByText("Сообщение удалено", { exact: true });
  const tombstonesBefore = await tombstones.count();
  await messageByBody(alicePage, `${original} edited`)
    .getByRole("button", { name: "Удалить" })
    .click();
  await expect(updated).toHaveCount(0);
  await expect(tombstones).toHaveCount(tombstonesBefore + 1);
  await Promise.all([alice.close(), outsider.close()]);
});

test("attachment IDOR and group admin policy hold on the live deployment", async ({
  browser,
}) => {
  const alice = await authenticatedContext(browser, "stage7-alice");
  const outsider = await authenticatedContext(browser, "stage7-outsider");
  const admin = await authenticatedContext(browser, "stage7-private-admin");
  const conversation = await group(alice);
  const upload = await alice.request.post(
    `/api/v1/messenger/conversations/${conversation.id}/attachments`,
    {
      multipart: {
        file: {
          name: "stage8-browser.pdf",
          mimeType: "application/pdf",
          buffer: Buffer.from("%PDF-1.7\n%%EOF\n"),
        },
      },
    },
  );
  expect(upload.status()).toBe(201);
  const asset = await upload.json();
  const sent = await alice.request.post(
    `/api/v1/messenger/conversations/${conversation.id}/messages`,
    {
      data: {
        client_message_id: crypto.randomUUID(),
        attachment_ids: [asset.id],
      },
    },
  );
  expect(sent.status()).toBe(201);
  const message = await sent.json();
  expect((await outsider.request.get(asset.content_url)).status()).toBe(200);
  expect((await admin.request.get(asset.content_url)).status()).toBe(404);

  const outsiderAccount = (
    await (
      await admin.request.get("/api/v1/platform/users?search=stage7-outsider")
    ).json()
  ).find(
    (account: { username: string }) => account.username === "stage7-outsider",
  );
  const rolePath = `/api/v1/messenger/conversations/${conversation.id}/members/${outsiderAccount.id}`;
  expect(
    (
      await outsider.request.put(`/api/v1/messenger/messages/${message.id}/pin`)
    ).status(),
  ).toBe(403);
  expect(
    (await alice.request.patch(rolePath, { data: { role: "ADMIN" } })).status(),
  ).toBe(200);
  expect(
    (
      await outsider.request.put(`/api/v1/messenger/messages/${message.id}/pin`)
    ).status(),
  ).toBe(204);
  expect(
    (
      await alice.request.patch(rolePath, { data: { role: "MEMBER" } })
    ).status(),
  ).toBe(200);
  await Promise.all([alice.close(), outsider.close(), admin.close()]);
});

test("logout closes only the current device and mobile layouts stay bounded", async ({
  browser,
}) => {
  const first = await authenticatedContext(browser, "stage7-alice");
  const second = await authenticatedContext(browser, "stage7-alice");
  const firstPage = await first.newPage();
  const secondPage = await second.newPage();
  await Promise.all([openGroup(firstPage), openGroup(secondPage)]);
  await firstPage.getByRole("button", { name: "Выйти" }).click();
  await expect(firstPage).toHaveURL(/\/login$/);
  await expect(secondPage.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени подключены",
  );

  for (const width of [360, 390, 768, 1440]) {
    await secondPage.setViewportSize({ width, height: 900 });
    await secondPage.goto("/messages");
    expect(
      await secondPage.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    await secondPage
      .getByRole("button", { name: new RegExp(groupTitle) })
      .click();
    await expect(secondPage.getByLabel("Сообщение")).toBeVisible();
    expect(
      await secondPage.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
  await Promise.all([first.close(), second.close()]);
});
