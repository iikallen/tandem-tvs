import {
  expect,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";

export const demoPassword =
  process.env.STAGE6_DEMO_PASSWORD ?? "Tandem development passphrase 2026";

export async function authenticateContext(
  context: BrowserContext,
  username = "employee-1",
  password = demoPassword,
) {
  const csrfResponse = await context.request.get("/api/v1/auth/csrf");
  expect(csrfResponse.status()).toBe(200);
  const { csrf_token: csrfToken } = await csrfResponse.json();
  const loginResponse = await context.request.post("/api/v1/auth/login", {
    headers: { "X-CSRFToken": csrfToken },
    data: { username, password },
  });
  expect(loginResponse.status()).toBe(200);
  const loginPayload = await loginResponse.json();
  await context.setExtraHTTPHeaders({
    "X-CSRFToken": loginPayload.csrf_token,
  });
  return loginPayload.user;
}

export async function authenticatedContext(
  browser: Browser,
  username = "employee-1",
) {
  const context = await browser.newContext();
  await authenticateContext(context, username);
  return context;
}

export async function authenticatePage(page: Page, username = "employee-1") {
  return authenticateContext(page.context(), username);
}
