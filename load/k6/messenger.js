import { check, sleep } from "k6";
import http from "k6/http";

import { baseUrl, ensureAuthenticated, firstConversation } from "./auth.js";

export function messenger() {
  ensureAuthenticated();
  const conversation = firstConversation();
  if (conversation) {
    const history = http.get(
      `${baseUrl}/api/v1/messenger/conversations/${conversation.id}/messages?page_size=50`,
      { tags: { kind: "message_history" } },
    );
    check(history, {
      "message history loaded": (response) => response.status === 200,
    });
  }
  const notifications = http.get(
    `${baseUrl}/api/v1/notifications?page_size=50`,
    {
      tags: { kind: "notification_inbox" },
    },
  );
  check(notifications, {
    "notifications loaded": (response) => response.status === 200,
  });
  sleep(1);
}

export default messenger;
