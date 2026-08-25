import { check, sleep } from "k6";
import http from "k6/http";

import { baseUrl, ensureAuthenticated, requestParams } from "./auth.js";

export function browse() {
  ensureAuthenticated();
  const feed = http.get(
    `${baseUrl}/api/v1/news?page_size=20`,
    requestParams("feed"),
  );
  check(feed, { "feed loaded": (response) => response.status === 200 });
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
  sleep(1);
}

export default browse;
