import { expect, test, type APIRequestContext } from "@playwright/test";

import { authenticatedContext, demoPassword } from "./auth";

test.describe.configure({ mode: "serial", timeout: 60_000 });

const activationPassword = "Stage six browser acceptance passphrase 2026";

async function createAccount(
  request: APIRequestContext,
  username: string,
  grants: Array<{ module: string; role: string }>,
) {
  const created = await request.post("/api/v1/platform/users", {
    data: {
      username,
      full_name: `Stage 6 ${username}`,
      email: `${username}@example.invalid`,
      grants,
    },
  });
  expect(created.status()).toBe(201);
  return created.json();
}

test("anonymous user logs in, comments, logs out and loses API access", async ({
  page,
}) => {
  const comment = `Stage 6 browser comment ${Date.now()}`;
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Логин").fill("employee-1");
  await page.getByLabel("Пароль").fill(demoPassword);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).toHaveURL(/\/news$/);

  await page.goto("/news/00000000-0000-0000-0000-000000003001");
  await page.getByLabel("Комментарий", { exact: true }).fill(comment);
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(page.getByText(comment)).toBeVisible();

  await page.getByRole("button", { name: "Выйти" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/v1/me")).status()).toBe(403);
});

test("editor can create a draft while a member cannot open Editorial", async ({
  browser,
}) => {
  const suffix = Date.now().toString();
  const editor = await authenticatedContext(browser, "editor-1");
  const created = await editor.request.post("/api/v1/editorial/publications", {
    data: {
      title: `Stage 6 auth draft ${suffix}`,
      summary: "Authenticated editor acceptance",
      body: { type: "doc", content: [] },
      category: "regulations",
      audience: {
        everyone: true,
        org_units: [],
        org_unit_subtrees: [],
        employees: [],
        module_roles: [],
        position_groups: [],
      },
    },
  });
  expect(created.status()).toBe(201);
  const editorPage = await editor.newPage();
  await editorPage.goto("/editorial/publications");
  await expect(
    editorPage.getByText(`Stage 6 auth draft ${suffix}`),
  ).toBeVisible();

  const member = await authenticatedContext(browser, "employee-1");
  const memberPage = await member.newPage();
  await memberPage.goto("/editorial/publications");
  await expect(memberPage.getByRole("alert")).toBeVisible();
  expect(
    (await member.request.get("/api/v1/editorial/publications")).status(),
  ).toBe(403);

  await Promise.all([editor.close(), member.close()]);
});

test("platform admin creates and disables an activated account", async ({
  browser,
}) => {
  const username = `stage6-disabled-${Date.now()}`;
  const admin = await authenticatedContext(browser, "admin-1");
  const adminPage = await admin.newPage();
  await adminPage.goto("/platform/users");
  const form = adminPage.locator(".user-create-grid");
  await form.getByLabel("Логин").fill(username);
  await form.getByLabel("ФИО").fill(`Stage 6 ${username}`);
  await form
    .getByLabel("Электронная почта")
    .fill(`${username}@example.invalid`);
  await form.getByRole("button", { name: "Создать пользователя" }).click();
  const activationUrl = await adminPage
    .getByLabel("Одноразовая ссылка")
    .inputValue();

  const employee = await browser.newContext();
  const employeePage = await employee.newPage();
  await employeePage.goto(activationUrl);
  await employeePage.getByLabel("Новый пароль").fill(activationPassword);
  await employeePage.getByLabel("Повторите пароль").fill(activationPassword);
  await employeePage
    .getByRole("button", { name: "Активировать аккаунт" })
    .click();
  await expect(employeePage.getByRole("status")).toHaveText("Пароль сохранён.");
  await employeePage.goto("/login");
  await employeePage.getByLabel("Логин").fill(username);
  await employeePage.getByLabel("Пароль").fill(activationPassword);
  await employeePage.getByRole("button", { name: "Войти" }).click();
  await expect(employeePage).toHaveURL(/\/news$/);

  await adminPage.getByLabel("Поиск пользователей").fill(username);
  const row = adminPage
    .locator(".user-row")
    .filter({ hasText: `@${username}` });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Отключить" }).click();
  await expect(row.getByText("Отключён")).toBeVisible();
  expect((await employee.request.get("/api/v1/me")).status()).toBe(403);

  await Promise.all([admin.close(), employee.close()]);
});

test("one account gains Messenger entitlement without a new password", async ({
  browser,
}) => {
  const username = `stage6-entitlement-${Date.now()}`;
  const admin = await authenticatedContext(browser, "admin-1");
  const account = await createAccount(admin.request, username, [
    { module: "NEWS", role: "MEMBER" },
  ]);
  const invitation = await admin.request.post(
    `/api/v1/platform/users/${account.id}/invitation`,
  );
  expect(invitation.status()).toBe(200);
  const { activation_url: activationUrl } = await invitation.json();

  const member = await browser.newContext();
  const page = await member.newPage();
  await page.goto(activationUrl);
  await page.getByLabel("Новый пароль").fill(activationPassword);
  await page.getByLabel("Повторите пароль").fill(activationPassword);
  await page.getByRole("button", { name: "Активировать аккаунт" }).click();
  await expect(page.getByRole("status")).toHaveText("Пароль сохранён.");
  await page.goto("/login");
  await page.getByLabel("Логин").fill(username);
  await page.getByLabel("Пароль").fill(activationPassword);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).toHaveURL(/\/news$/);
  expect((await member.request.get("/api/v1/messenger/access")).status()).toBe(
    403,
  );
  await page.goto("/messages");
  await expect(page).toHaveURL(/\/$/);

  const granted = await admin.request.put(
    `/api/v1/platform/users/${account.id}/grants/MESSENGER/MEMBER`,
  );
  expect(granted.status()).toBe(204);
  await page.goto("/messages");
  await expect(
    page.getByRole("heading", { name: "Доступ к Messenger назначен" }),
  ).toBeVisible();

  await Promise.all([admin.close(), member.close()]);
});

for (const width of [360, 390, 768, 1440]) {
  test(`login is usable without horizontal overflow at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Войти" })).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  });
}
