import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { authenticatedContext } from "./auth";

test.describe.configure({ mode: "serial", timeout: 90_000 });

const channelTitle = "Stage 9 Acceptance Channel";

async function channel(request: APIRequestContext) {
  const response = await request.get("/api/v1/messenger/conversations");
  expect(response.status()).toBe(200);
  const payload = await response.json();
  const result = payload.results.find(
    (conversation: { title: string }) => conversation.title === channelTitle,
  );
  expect(result).toBeTruthy();
  return result;
}

async function notificationRows(request: APIRequestContext) {
  const response = await request.get("/api/v1/notifications?unread=true");
  expect(response.status()).toBe(200);
  return (await response.json()).results;
}

async function assertBounded(page: Page) {
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
}

test("two devices synchronize grouped notifications and open the exact message", async ({
  browser,
}) => {
  const first = await authenticatedContext(browser, "stage9-member");
  const second = await authenticatedContext(browser, "stage9-member");
  const admin = await authenticatedContext(browser, "stage9-admin");
  const conversation = await channel(first.request);
  await new Promise((resolve) => setTimeout(resolve, 3_000));
  await first.request.post("/api/v1/notifications/read-all");
  await expect
    .poll(async () => (await notificationRows(first.request)).length)
    .toBe(0);
  await first.request.patch(
    `/api/v1/messenger/conversations/${conversation.id}/state`,
    { data: { notification_mode: "ALL", muted_until: null } },
  );
  const firstPage = await first.newPage();
  const secondPage = await second.newPage();
  await Promise.all([
    firstPage.goto("/notifications"),
    secondPage.goto("/notifications"),
  ]);

  const messageIds: string[] = [];
  for (let index = 0; index < 3; index += 1) {
    const response = await admin.request.post(
      `/api/v1/messenger/conversations/${conversation.id}/messages`,
      {
        data: {
          client_message_id: crypto.randomUUID(),
          body: `Stage 9 grouped browser message ${index}`,
          kind: "CHANNEL_POST",
        },
      },
    );
    expect(response.status()).toBe(201);
    messageIds.push((await response.json()).id);
  }
  await expect
    .poll(
      async () =>
        (await notificationRows(second.request)).find(
          (row: { notification_type: string }) =>
            row.notification_type === "NEW_MESSAGE",
        )?.occurrence_count,
      { timeout: 15_000 },
    )
    .toBe(3);
  await expect(firstPage.getByText("Событий: 3").last()).toBeVisible({
    timeout: 10_000,
  });
  await expect(secondPage.locator(".notification-bell span")).toHaveText("1");

  const target = messageIds.at(-1)!;
  const targetHref = `/messages?conversation=${conversation.id}&message=${target}`;
  const grouped = firstPage.locator(".notification-card").filter({
    has: firstPage.locator(`a[href="${targetHref}"]`),
  });
  await expect(grouped.getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    targetHref,
  );
  await grouped.getByRole("link", { name: "Открыть" }).click();
  await expect(firstPage.locator(`#message-${target}`)).toHaveClass(
    /messenger-message--target/,
  );
  await expect(secondPage.locator(".notification-bell span")).toHaveCount(0, {
    timeout: 10_000,
  });

  const mentionResponse = await admin.request.post(
    `/api/v1/messenger/conversations/${conversation.id}/messages`,
    {
      data: {
        client_message_id: crypto.randomUUID(),
        body: "Stage 9 browser mention",
        kind: "CHANNEL_POST",
        mentioned_user_ids: [
          (
            await (
              await admin.request.get(
                "/api/v1/messenger/people?search=stage9-member",
              )
            ).json()
          )[0].id,
        ],
      },
    },
  );
  expect(mentionResponse.status()).toBe(201);
  await expect
    .poll(
      async () =>
        (await notificationRows(second.request)).some(
          (row: { notification_type: string }) =>
            row.notification_type === "MESSAGE_MENTION",
        ),
      { timeout: 15_000 },
    )
    .toBe(true);
  await secondPage.reload();
  await expect(
    secondPage.getByText("упоминает вас в сообщении").last(),
  ).toBeVisible();
  await Promise.all([first.close(), second.close(), admin.close()]);
});

test("global search privacy, channel policy, keyboard access and responsive widths hold", async ({
  browser,
}) => {
  const member = await authenticatedContext(browser, "stage9-member");
  const writer = await authenticatedContext(browser, "stage9-editor");
  const channelAdmin = await authenticatedContext(browser, "stage9-admin");
  const outsider = await authenticatedContext(browser, "stage9-outsider");
  const unrelatedAdmin = await authenticatedContext(
    browser,
    "stage7-private-admin",
  );
  const conversation = await channel(member.request);
  const path = `/api/v1/messenger/conversations/${conversation.id}/messages`;
  expect(
    (
      await channelAdmin.request.patch(
        `/api/v1/messenger/conversations/${conversation.id}`,
        { data: { discussion_enabled: false } },
      )
    ).status(),
  ).toBe(200);
  expect(
    (
      await member.request.post(path, {
        data: {
          client_message_id: crypto.randomUUID(),
          body: "member discussion is disabled",
          kind: "DISCUSSION",
        },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await channelAdmin.request.patch(
        `/api/v1/messenger/conversations/${conversation.id}`,
        { data: { discussion_enabled: true } },
      )
    ).status(),
  ).toBe(200);
  expect(
    (
      await member.request.post(path, {
        data: {
          client_message_id: crypto.randomUUID(),
          body: "member cannot publish",
          kind: "CHANNEL_POST",
        },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await member.request.post(path, {
        data: {
          client_message_id: crypto.randomUUID(),
          body: "member discussion is allowed",
          kind: "DISCUSSION",
        },
      })
    ).status(),
  ).toBe(201);
  expect(
    (
      await writer.request.post(path, {
        data: {
          client_message_id: crypto.randomUUID(),
          body: "writer channel post",
          kind: "CHANNEL_POST",
        },
      })
    ).status(),
  ).toBe(201);
  expect((await unrelatedAdmin.request.get(path)).status()).toBe(404);

  const visibleSearch = await member.request.get("/api/v1/search?q=маяк");
  expect(visibleSearch.status()).toBe(200);
  const visiblePayload = await visibleSearch.json();
  expect(Object.values(visiblePayload).every((rows) => rows.length > 0)).toBe(
    true,
  );
  const privateSearch = await outsider.request.get("/api/v1/search?q=маяк");
  expect(privateSearch.status()).toBe(200);
  const privatePayload = await privateSearch.json();
  expect(
    ["publications", "comments", "messages", "files"].every(
      (scope) => privatePayload[scope].length === 0,
    ),
  ).toBe(true);

  const page = await member.newPage();
  await page.goto("/");
  await page.getByLabel("Глобальный поиск").fill("маяк");
  await page.getByLabel("Глобальный поиск").press("Enter");
  await expect(page).toHaveURL(/\/search\?q=/);
  for (const heading of [
    "Публикации",
    "Комментарии",
    "Сообщения",
    "Файлы",
    "Сотрудники",
  ]) {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
  await expect(
    page.getByRole("link", { name: /Stage 9 Acceptance Channel/ }).first(),
  ).toHaveAttribute("href", /\/messages\?conversation=.*&message=/);

  for (const width of [360, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/notifications");
    await assertBounded(page);
    await page.goto("/search?q=маяк");
    await expect(
      page.getByRole("heading", { name: "Публикации" }),
    ).toBeVisible();
    await assertBounded(page);
  }
  await Promise.all([
    member.close(),
    writer.close(),
    channelAdmin.close(),
    outsider.close(),
    unrelatedAdmin.close(),
  ]);
});
