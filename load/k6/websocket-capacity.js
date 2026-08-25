import { sleep } from "k6";
import http from "k6/http";
import { Rate, Trend } from "k6/metrics";

import { baseUrl } from "./auth.js";
import { realtime } from "./websocket.js";

const activeSockets = new Trend("tandem_active_socket_observed");
const monitorFailures = new Rate("tandem_ops_monitor_failures");

export const options = {
  scenarios: {
    messenger_sockets: {
      executor: "per-vu-iterations",
      vus: 300,
      iterations: 1,
      maxDuration: "16m",
    },
    socket_monitor: {
      executor: "constant-vus",
      exec: "monitorSockets",
      vus: 1,
      startTime: "10s",
      duration: "15m30s",
    },
  },
  thresholds: {
    ws_connecting: ["p(95)<2000"],
    tandem_ws_full_duration_success: ["rate==1"],
    tandem_ws_sessions_completed: ["count==300"],
    tandem_active_socket_observed: ["max>=300"],
    tandem_ops_monitor_failures: ["rate<0.01"],
    tandem_realtime_failures: ["rate<0.01"],
  },
};

export default function () {
  realtime(900000, false);
}

export function monitorSockets() {
  const token = __ENV.OPS_MONITORING_TOKEN;
  if (!token) {
    monitorFailures.add(1);
    throw new Error("OPS_MONITORING_TOKEN is required");
  }
  const response = http.get(`${baseUrl}/internal/metrics`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { kind: "ops_monitor" },
  });
  const match = /^tandem_active_realtime_sockets ([0-9]+)$/m.exec(
    response.body || "",
  );
  monitorFailures.add(response.status !== 200 || !match);
  if (match) activeSockets.add(Number(match[1]));
  sleep(5);
}
