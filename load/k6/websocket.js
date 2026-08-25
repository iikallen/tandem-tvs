import { check } from "k6";
import http from "k6/http";
import { Counter, Rate, Trend } from "k6/metrics";
import { WebSocket } from "k6/websockets";

import {
  baseUrl,
  ensureAuthenticated,
  firstConversation,
  jsonParams,
  wsBaseUrl,
} from "./auth.js";

export const realtimeFailures = new Rate("tandem_realtime_failures");
export const realtimeDelivery = new Trend("tandem_realtime_delivery_ms", true);
export const fullDurationSuccess = new Rate("tandem_ws_full_duration_success");
export const completedSessions = new Counter("tandem_ws_sessions_completed");

function clientMessageId() {
  const prefix = __VU.toString(16).padStart(8, "0");
  const suffix = Date.now().toString(16).slice(-12).padStart(12, "0");
  return `${prefix}-0000-4000-8000-${suffix}`;
}

export function realtime(
  holdMs = Number(__ENV.WS_HOLD_MS || "60000"),
  emitMessage = true,
) {
  let durationRecorded = false;
  const recordDuration = (success) => {
    if (durationRecorded) return;
    durationRecorded = true;
    completedSessions.add(1);
    fullDurationSuccess.add(success);
  };
  ensureAuthenticated();
  const conversation = firstConversation();
  if (!conversation) {
    realtimeFailures.add(1);
    recordDuration(false);
    return;
  }
  const ticket = http.post(
    `${baseUrl}/api/v1/realtime/tickets`,
    JSON.stringify({ scope: "MESSENGER" }),
    jsonParams("realtime_ticket"),
  );
  if (
    !check(ticket, {
      "realtime ticket issued": (response) => response.status === 200,
    })
  ) {
    realtimeFailures.add(1);
    recordDuration(false);
    return;
  }

  const socket = new WebSocket(
    `${wsBaseUrl}/ws/v1/messenger?ticket=${encodeURIComponent(ticket.json("ticket"))}`,
  );
  let pendingMessageId = "";
  let sentAt = 0;
  let pingAt = 0;
  let openedAt = 0;
  let closeTimer;
  let pingTimer;

  socket.addEventListener("open", () => {
    openedAt = Date.now();
    realtimeFailures.add(0);
    pingTimer = setInterval(() => {
      pingAt = Date.now();
      socket.send(JSON.stringify({ type: "ping" }));
    }, 10000);
    if (emitMessage) {
      const requestId = clientMessageId();
      sentAt = Date.now();
      const response = http.post(
        `${baseUrl}/api/v1/messenger/conversations/${conversation.id}/messages`,
        JSON.stringify({
          client_message_id: requestId,
          body: `k6 realtime ${requestId}`,
        }),
        jsonParams("realtime_message_write"),
      );
      check(response, {
        "realtime source message committed": (item) =>
          [200, 201].includes(item.status),
      });
      if ([200, 201].includes(response.status))
        pendingMessageId = response.json("id");
    }
    closeTimer = setTimeout(() => socket.close(), holdMs);
  });
  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "pong" && pingAt)
      realtimeDelivery.add(Date.now() - pingAt, { kind: "ping" });
    if (
      pendingMessageId &&
      payload.type === "messenger.message.created" &&
      payload.message_id === pendingMessageId
    ) {
      realtimeDelivery.add(Date.now() - sentAt, { kind: "message" });
      pendingMessageId = "";
    }
  });
  socket.addEventListener("error", () => realtimeFailures.add(1));
  socket.addEventListener("close", () => {
    clearInterval(pingTimer);
    clearTimeout(closeTimer);
    if (pendingMessageId) realtimeFailures.add(1);
    recordDuration(openedAt > 0 && Date.now() - openedAt >= holdMs - 5000);
  });
}

export default realtime;
