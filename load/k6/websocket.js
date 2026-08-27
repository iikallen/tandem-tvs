import { check } from "k6";
import http from "k6/http";
import { Counter, Rate, Trend } from "k6/metrics";
import ws from "k6/ws";

import {
  baseUrl,
  ensureAuthenticated,
  firstConversation,
  jsonParams,
  websocketParams,
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

  let pendingMessageId = "";
  let sentAt = 0;
  let pingAt = 0;
  let openedAt = 0;
  const response = ws.connect(
    `${wsBaseUrl}/ws/v1/messenger?ticket=${encodeURIComponent(ticket.json("ticket"))}`,
    websocketParams(),
    (socket) => {
      socket.on("open", () => {
        openedAt = Date.now();
        realtimeFailures.add(0);
        socket.setInterval(() => {
          pingAt = Date.now();
          socket.send(JSON.stringify({ type: "ping" }));
        }, 10000);
        if (emitMessage) {
          const requestId = clientMessageId();
          sentAt = Date.now();
          const message = http.post(
            `${baseUrl}/api/v1/messenger/conversations/${conversation.id}/messages`,
            JSON.stringify({
              client_message_id: requestId,
              body: `k6 realtime ${requestId}`,
            }),
            jsonParams("realtime_message_write"),
          );
          check(message, {
            "realtime source message committed": (item) =>
              [200, 201].includes(item.status),
          });
          if ([200, 201].includes(message.status))
            pendingMessageId = message.json("id");
        }
        socket.setTimeout(() => socket.close(), holdMs);
      });
      socket.on("message", (data) => {
        const payload = JSON.parse(data);
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
      socket.on("error", (error) => {
        console.error(`WebSocket error: ${error.error()}`);
        realtimeFailures.add(1);
      });
      socket.on("close", () => {
        if (pendingMessageId) realtimeFailures.add(1);
        recordDuration(openedAt > 0 && Date.now() - openedAt >= holdMs - 5000);
      });
    },
  );
  if (!response || response.status !== 101) {
    realtimeFailures.add(1);
    recordDuration(false);
  }
}

export default realtime;
