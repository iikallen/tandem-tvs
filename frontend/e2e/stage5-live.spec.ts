import { expect, test, type Page } from "@playwright/test";

import { authenticatedContext } from "./auth";

test.describe.configure({ mode: "serial" });

async function expectRealtimeConnected(page: Page) {
  await expect(
    page.getByText("Обновления в реальном времени подключены"),
  ).toBeVisible({ timeout: 15_000 });
}

test("thread, mention notification, reactions, acknowledgement and moderation work live", async ({
  browser,
}) => {
  const replyBody = `Ответ участника ${Date.now()}`;
  const editor = await authenticatedContext(browser, "editor-1");
  await editor.request.patch("/api/v1/editorial/settings/engagement", {
    data: { enabled_reaction_types: ["LIKE", "INSIGHTFUL"] },
  });
  const localEmployees = await (
    await editor.request.get("/api/v1/organization/employees?search=employee-1")
  ).json();
  const localAuthors = await (
    await editor.request.get("/api/v1/organization/employees?search=author-1")
  ).json();
  const employeeId = localEmployees.find(
    (employee: { portal_id: string }) => employee.portal_id === "employee-1",
  ).id;
  const authorId = localAuthors.find(
    (employee: { portal_id: string }) => employee.portal_id === "author-1",
  ).id;
  const draftResponse = await editor.request.post(
    "/api/v1/editorial/publications",
    {
      data: {
        title: `Stage 5 live ${Date.now()}`,
        summary: "Playwright engagement acceptance",
        body: {
          type: "doc",
          content: [
            {
              type: "paragraph",
              content: [{ type: "text", text: "Stage 5 live body" }],
            },
          ],
        },
        category: "regulations",
        comments_enabled: true,
        reactions_enabled: true,
        acknowledgement_required: true,
        audience: {
          everyone: false,
          org_units: [],
          org_unit_subtrees: [],
          employees: [employeeId, authorId],
          module_roles: [],
          position_groups: [],
        },
      },
    },
  );
  expect(draftResponse.status()).toBe(201);
  const draft = await draftResponse.json();
  expect(
    (
      await editor.request.post(
        `/api/v1/editorial/publications/${draft.id}/publish`,
        { data: { expected_revision: draft.edit_revision } },
      )
    ).status(),
  ).toBe(200);

  const employee = await authenticatedContext(browser, "employee-1");
  const participant = await authenticatedContext(browser, "author-1");
  const moderator = await authenticatedContext(browser, "admin-1");
  await moderator.request.delete(
    "/api/v1/editorial/moderation/users/author-1/restriction",
  );
  expect(
    (await moderator.request.get(`/api/v1/news/${draft.id}`)).status(),
  ).toBe(404);
  expect(
    (
      await moderator.request.post("/api/v1/realtime/tickets", {
        data: { publication_id: draft.id },
      })
    ).status(),
  ).toBe(404);
  const employeePage = await employee.newPage();
  const participantPage = await participant.newPage();
  await Promise.all([
    employeePage.goto(`/news/${draft.id}`),
    participantPage.goto(`/news/${draft.id}`),
  ]);
  await Promise.all([
    expectRealtimeConnected(employeePage),
    expectRealtimeConnected(participantPage),
  ]);
  await employeePage.getByLabel("Комментарий").fill("Коллеги, посмотрите");
  await employeePage.getByLabel("Упомянуть сотрудника").fill("Серик");
  await employeePage.getByRole("button", { name: "@Серик Жаксибеков" }).click();
  await employeePage.getByRole("button", { name: "Отправить" }).click();
  await expect(participantPage.getByText(/@Серик Жаксибеков/)).toBeVisible({
    timeout: 5_000,
  });

  await participantPage.goto("/notifications");
  await expect(
    participantPage.getByText("Алия Байжанова").first(),
  ).toBeVisible();
  await expect(
    participantPage.getByText("упоминает вас в комментарии").first(),
  ).toBeVisible();
  await participantPage.goto(`/news/${draft.id}`);
  await expectRealtimeConnected(participantPage);

  const root = (
    await (
      await employee.request.get(`/api/v1/news/${draft.id}/comments`)
    ).json()
  ).results[0];
  const replyResponse = await participant.request.post(
    `/api/v1/news/${draft.id}/comments`,
    {
      data: {
        body: replyBody,
        reply_to: root.id,
      },
    },
  );
  expect(replyResponse.status()).toBe(201);
  const reply = await replyResponse.json();
  await expect(employeePage.getByText(replyBody)).toBeVisible({
    timeout: 5_000,
  });
  await participantPage.getByRole("button", { name: /Полезно/ }).click();
  await expect(
    employeePage.getByRole("button", { name: /Полезно: 1/ }),
  ).toBeVisible({
    timeout: 5_000,
  });
  await employeePage
    .getByRole("button", { name: "Подтвердить ознакомление" })
    .click();
  await expect(
    employeePage.getByText("Ознакомление подтверждено"),
  ).toBeVisible();
  await participantPage
    .getByRole("button", { name: "Подтвердить ознакомление" })
    .click();

  await employeePage.goto("/notifications");
  await expect(
    employeePage.getByText("Серик Жаксибеков").first(),
  ).toBeVisible();
  await expect(
    employeePage.getByText("ответил(а) на ваш комментарий").first(),
  ).toBeVisible();
  await employeePage.goto(`/news/${draft.id}`);
  await expectRealtimeConnected(employeePage);

  await employee.request.post(
    `/api/v1/news/${draft.id}/comments/${reply.id}/reports`,
    { data: { reason: "E2E moderation" } },
  );
  const moderatorPage = await moderator.newPage();
  await moderatorPage.goto("/editorial/moderation");
  const reportCard = moderatorPage.locator(".moderation-card").filter({
    hasText: replyBody,
  });
  await expect(reportCard).toBeVisible();
  await reportCard.getByRole("button", { name: "Скрыть" }).click();
  await expect(
    employeePage.getByText("Комментарий скрыт на время модерации"),
  ).toBeVisible({ timeout: 5_000 });

  expect(
    (
      await moderator.request.post(
        `/api/v1/editorial/moderation/comments/${reply.id}/restore`,
      )
    ).status(),
  ).toBe(200);
  await expect(employeePage.getByText(replyBody)).toBeVisible({
    timeout: 5_000,
  });
  expect(
    (
      await moderator.request.post(
        "/api/v1/editorial/moderation/users/author-1/restriction",
        { data: { hours: 24 } },
      )
    ).status(),
  ).toBe(201);
  expect(
    (
      await participant.request.post(`/api/v1/news/${draft.id}/comments`, {
        data: { body: "Ограничение должно блокировать отправку" },
      })
    ).status(),
  ).toBe(403);
  await moderator.request.delete(
    "/api/v1/editorial/moderation/users/author-1/restriction",
  );

  for (const width of [360, 390, 768, 1440]) {
    await employeePage.setViewportSize({ width, height: 900 });
    expect(
      await employeePage.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
  await Promise.all([
    employee.close(),
    participant.close(),
    moderator.close(),
    editor.close(),
  ]);
});
