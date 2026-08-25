import { check, sleep } from "k6";
import http from "k6/http";

import { baseUrl, ensureAuthenticated, requestParams } from "./auth.js";

const thinkSeconds = Number(
  __ENV.THINK_SECONDS || (__ENV.PROFILE === "smoke" ? "1" : "10"),
);

export function browse() {
  ensureAuthenticated();
  const feed = http.get(
    `${baseUrl}/api/v1/news?page_size=20`,
    requestParams("feed"),
  );
  const feedLoaded = check(feed, {
    "feed loaded": (response) => response.status === 200,
  });
  if (!feedLoaded) {
    sleep(thinkSeconds);
    return;
  }
  const rows = feed.json("results") || [];
  if (rows.length) {
    const detail = http.get(
      `${baseUrl}/api/v1/news/${rows[0].id}`,
      requestParams("publication_detail"),
    );
    check(detail, {
      "publication loaded": (response) => response.status === 200,
    });
  }
  const search = http.get(
    `${baseUrl}/api/v1/search?q=${encodeURIComponent("безопасность қауіпсіздік")}`,
    requestParams("search"),
  );
  check(search, { "search loaded": (response) => response.status === 200 });
  sleep(thinkSeconds);
}

export default browse;
