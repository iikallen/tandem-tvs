import { check, sleep } from "k6";
import http from "k6/http";

import {
  baseUrl,
  ensureAuthenticated,
  firstConversation,
  requestParams,
} from "./auth.js";

const thinkSeconds = Number(
  __ENV.THINK_SECONDS || (__ENV.PROFILE === "smoke" ? "1" : "30"),
);

export function messenger() {
  ensureAuthenticated();
  const conversation = firstConversation();
  if (conversation) {
    const history = http.get(
      `${baseUrl}/api/v1/messenger/conversations/${conversation.id}/messages?page_size=50`,
      requestParams("message_history"),
    );
    check(history, {
      "message history loaded": (response) => response.status === 200,
    });
  }
  const notifications = http.get(
    `${baseUrl}/api/v1/notifications?page_size=50`,
    requestParams("notification_inbox"),
  );
  check(notifications, {
    "notifications loaded": (response) => response.status === 200,
  });
  sleep(thinkSeconds);
}

export default messenger;
