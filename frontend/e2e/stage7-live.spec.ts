import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { authenticateContext, authenticatedContext } from "./auth";

test.describe.configure({ mode: "serial", timeout: 60_000 });

const directTitle = "Болат Stage 7";
const aliceTitle = "Алия Stage 7";

async function openConversation(page: Page, title: string) {
  await page.goto("/messages");
  await expect(page.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени подключены",
  );
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

async function directConversation(request: APIRequestContext) {
  const response = await request.get("/api/v1/messenger/conversations");
  expect(response.status()).toBe(200);
  const conversations = await response.json();
  return conversations.find(
    (conversation: {
      type: string;
      members: Array<{ user: { username: string } }>;
    }) =>
      conversation.type === "DIRECT" &&
      conversation.members.some(
        (membership) => membership.user.username === "stage7-bob",
      ),
  );
}

test("two browsers receive a persisted direct message in under one second", async ({
  browser,
}) => {
  const body = `Stage 7 browser realtime ${Date.now()}`;
  const alice = await authenticatedContext(browser, "stage7-alice");
  const bob = await authenticatedContext(browser, "stage7-bob");
  const alicePage = await alice.newPage();
  const bobPage = await bob.newPage();
  await Promise.all([
    openConversation(alicePage, directTitle),
    openConversation(bobPage, aliceTitle),
  ]);

  await alicePage.getByLabel("Сообщение").fill(body);
  const started = Date.now();
  await alicePage.getByRole("button", { name: "Отправить" }).click();
  await expect(
    bobPage.locator(".messenger-message p").filter({ hasText: body }),
  ).toBeVisible({ timeout: 999 });
  expect(Date.now() - started).toBeLessThan(1_000);

  await bobPage.reload();
  await bobPage.getByRole("button", { name: new RegExp(aliceTitle) }).click();
  await expect(
    bobPage.locator(".messenger-message p").filter({ hasText: body }),
  ).toBeVisible();
  await Promise.all([alice.close(), bob.close()]);
});

test("a lost response retries the same client UUID without a duplicate", async ({
  browser,
}) => {
  const body = `Stage 7 idempotent retry ${Date.now()}`;
  const alice = await authenticatedContext(browser, "stage7-alice");
  const bob = await authenticatedContext(browser, "stage7-bob");
  const alicePage = await alice.newPage();
  const bobPage = await bob.newPage();
  await Promise.all([
    openConversation(alicePage, directTitle),
    openConversation(bobPage, aliceTitle),
  ]);

  const conversation = await directConversation(alice.request);
  const historyPath = `/api/v1/messenger/conversations/${conversation.id}/messages`;
  const staleHistory = await (await alice.request.get(historyPath)).json();
  let intercepted = false;
  await alicePage.route(
    "**/api/v1/messenger/conversations/*/messages",
    async (route) => {
      if (route.request().method() === "POST" && !intercepted) {
        intercepted = true;
        await route.fetch();
        await route.abort("failed");
        return;
      }
      if (route.request().method() === "GET") {
        await route.fulfill({ json: staleHistory });
        return;
      }
      await route.continue();
    },
  );
  await alicePage.getByLabel("Сообщение").fill(body);
  await alicePage.getByRole("button", { name: "Отправить" }).click();
  await alicePage.getByRole("button", { name: "Повторить" }).click();
  await expect(
    alicePage.locator(".messenger-message p").filter({ hasText: body }),
  ).toHaveCount(1);
  await expect(
    bobPage.locator(".messenger-message p").filter({ hasText: body }),
  ).toHaveCount(1);

  const history = await (await alice.request.get(historyPath)).json();
  expect(
    history.messages.filter(
      (message: { body: string }) => message.body === body,
    ),
  ).toHaveLength(1);
  await Promise.all([alice.close(), bob.close()]);
});

test("group messages, unread state and responsive one-pane layouts work", async ({
  browser,
}) => {
  const body = `Stage 7 group browser ${Date.now()}`;
  const alice = await authenticatedContext(browser, "stage7-alice");
  const bob = await authenticatedContext(browser, "stage7-bob");
  const alicePage = await alice.newPage();
  const bobPage = await bob.newPage();
  await Promise.all([
    openConversation(alicePage, "Stage 7 Acceptance Group"),
    openConversation(bobPage, "Stage 7 Acceptance Group"),
  ]);
  await alicePage.getByLabel("Сообщение").fill(body);
  await alicePage.getByLabel("Сообщение").press("Enter");
  await expect(
    bobPage.locator(".messenger-message p").filter({ hasText: body }),
  ).toBeVisible();

  for (const width of [360, 390, 768, 1440]) {
    await alicePage.setViewportSize({ width, height: 900 });
    await alicePage.goto("/messages");
    expect(
      await alicePage.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
    await alicePage
      .getByRole("button", { name: /Stage 7 Acceptance Group/ })
      .click();
    await expect(alicePage.getByLabel("Сообщение")).toBeVisible();
    expect(
      await alicePage.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
  await Promise.all([alice.close(), bob.close()]);
});

test("outsider and platform admin cannot access a private conversation", async ({
  browser,
}) => {
  const alice = await authenticatedContext(browser, "stage7-alice");
  const outsider = await authenticatedContext(browser, "stage7-outsider");
  const admin = await authenticatedContext(browser, "stage7-private-admin");
  const conversation = await directConversation(alice.request);
  for (const context of [outsider, admin]) {
    expect(
      (
        await context.request.get(
          `/api/v1/messenger/conversations/${conversation.id}`,
        )
      ).status(),
    ).toBe(404);
    expect(
      (
        await context.request.get(
          `/api/v1/messenger/conversations/${conversation.id}/messages`,
        )
      ).status(),
    ).toBe(404);
    expect(
      (
        await context.request.post(
          `/api/v1/messenger/conversations/${conversation.id}/messages`,
          {
            data: {
              client_message_id: crypto.randomUUID(),
              body: "forbidden",
            },
          },
        )
      ).status(),
    ).toBe(404);
  }
  await Promise.all([alice.close(), outsider.close(), admin.close()]);
});

test("revoking access and disabling an account close existing sockets", async ({
  browser,
}) => {
  const bob = await authenticatedContext(browser, "stage7-bob");
  const admin = await authenticatedContext(browser, "stage7-private-admin");
  const bobPage = await bob.newPage();
  await openConversation(bobPage, aliceTitle);
  const people = await (
    await admin.request.get("/api/v1/platform/users?search=stage7-bob")
  ).json();
  const bobAccount = people.find(
    (account: { username: string }) => account.username === "stage7-bob",
  );
  const grantPath = `/api/v1/platform/users/${bobAccount.id}/grants/MESSENGER/MEMBER`;

  expect((await admin.request.delete(grantPath)).status()).toBe(204);
  await expect(bobPage.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени недоступны",
  );
  expect(
    (
      await bob.request.post("/api/v1/realtime/tickets", {
        data: { scope: "MESSENGER" },
      })
    ).status(),
  ).toBe(403);
  expect((await admin.request.put(grantPath)).status()).toBe(204);
  await authenticateContext(bob, "stage7-bob");
  await bobPage.goto("/messages");
  await expect(bobPage.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени подключены",
  );

  expect(
    (
      await admin.request.patch(`/api/v1/platform/users/${bobAccount.id}`, {
        data: { is_active: false },
      })
    ).status(),
  ).toBe(200);
  await expect(bobPage.locator(".messenger-status")).toHaveAttribute(
    "title",
    "Обновления в реальном времени недоступны",
  );
  expect(
    (
      await admin.request.patch(`/api/v1/platform/users/${bobAccount.id}`, {
        data: { is_active: true },
      })
    ).status(),
  ).toBe(200);
  await Promise.all([bob.close(), admin.close()]);
});
