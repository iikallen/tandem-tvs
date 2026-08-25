import { browse } from "./browse.js";
import { messenger } from "./messenger.js";
import { realtime } from "./websocket.js";

const smoke = __ENV.PROFILE === "smoke";
const duration = smoke ? "1m" : "30m";

export const options = {
  scenarios: {
    portal_readers: {
      executor: "constant-vus",
      exec: "browseScenario",
      vus: smoke ? 4 : 180,
      duration,
    },
    messenger_users: {
      executor: "constant-vus",
      exec: "messengerScenario",
      vus: smoke ? 2 : 90,
      duration,
    },
    active_realtime: {
      executor: "constant-vus",
      exec: "realtimeScenario",
      vus: smoke ? 2 : 30,
      duration,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{kind:feed}": ["p(95)<2000"],
    "http_req_duration{kind:publication_detail}": ["p(95)<2000"],
    "http_req_duration{kind:message_history}": ["p(95)<2000"],
    "http_req_duration{kind:search}": ["p(95)<2000"],
    "tandem_realtime_delivery_ms{kind:message}": ["p(95)<1000"],
    tandem_realtime_failures: ["rate<0.01"],
  },
};

export function browseScenario() {
  browse();
}

export function messengerScenario() {
  messenger();
}

export function realtimeScenario() {
  realtime(smoke ? 30000 : 60000, true);
}
