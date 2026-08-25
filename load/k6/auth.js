import { check, fail } from "k6";
import http from "k6/http";

export const baseUrl = (__ENV.BASE_URL || "http://localhost:8080").replace(
  /\/$/,
  "",
);
export const wsBaseUrl = (
  __ENV.WS_BASE_URL || baseUrl.replace(/^http/, "ws")
).replace(/\/$/, "");
const trustedOrigin =
  __ENV.TANDEM_ORIGIN || "https://tandem-tvs.chatlink.kz";
export const proxyHeaders =
  __ENV.TANDEM_TRUSTED_PROXY === "true"
    ? {
        Host: __ENV.TANDEM_HOST || "tandem-tvs.chatlink.kz",
        Origin: trustedOrigin,
        Referer: `${trustedOrigin}/`,
        "X-Forwarded-Proto": "https",
      }
    : {};

let csrfToken = "";
let authenticated = false;
const cookies = {};

function rememberCookies(response) {
  for (const [name, values] of Object.entries(response.cookies || {})) {
    if (values.length) cookies[name] = values[0].value;
  }
}

export function requestParams(kind, headers = {}) {
  const cookie = Object.entries(cookies)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return {
    headers: {
      ...proxyHeaders,
      ...(cookie ? { Cookie: cookie } : {}),
      ...headers,
    },
    tags: { kind },
  };
}

export function websocketParams() {
  return {
    headers: {
      ...requestParams("realtime_socket").headers,
      Origin: trustedOrigin,
    },
  };
}

function loadUsername() {
  const count = Number(__ENV.LOAD_USER_COUNT || "1000");
  const offset = Number(__ENV.LOAD_USER_OFFSET || "0");
  return `load-${(((offset + __VU - 1) % count) + 1).toString().padStart(4, "0")}`;
}

export function ensureAuthenticated() {
  if (authenticated) return csrfToken;
  const password = __ENV.TANDEM_LOAD_PASSWORD;
  if (!password) fail("TANDEM_LOAD_PASSWORD is required");
  const csrf = http.get(
    `${baseUrl}/api/v1/auth/csrf`,
    requestParams("auth"),
  );
  if (!check(csrf, { "csrf issued": (response) => response.status === 200 })) {
    fail(`CSRF request failed: ${csrf.status}`);
  }
  rememberCookies(csrf);
  csrfToken = csrf.json("csrf_token");
  const login = http.post(
    `${baseUrl}/api/v1/auth/login`,
    JSON.stringify({ username: loadUsername(), password }),
    requestParams("auth", {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    }),
  );
  if (
    !check(login, { "login succeeded": (response) => response.status === 200 })
  ) {
    fail(`Login failed for ${loadUsername()}: ${login.status}`);
  }
  rememberCookies(login);
  csrfToken = login.json("csrf_token");
  authenticated = true;
  return csrfToken;
}

export function jsonParams(kind) {
  return requestParams(kind, {
    "Content-Type": "application/json",
    "X-CSRFToken": ensureAuthenticated(),
  });
}

export function firstConversation() {
  ensureAuthenticated();
  const response = http.get(
    `${baseUrl}/api/v1/messenger/conversations?page_size=50`,
    requestParams("inbox"),
  );
  if (
    !check(response, {
      "conversation inbox loaded": (item) => item.status === 200,
    })
  )
    return null;
  const rows = response.json("results") || response.json("conversations") || [];
  return rows.find((row) => row.type !== "CHANNEL") || rows[0] || null;
}
