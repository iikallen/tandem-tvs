import { browse } from "./browse.js";
import { messenger } from "./messenger.js";
import { realtime } from "./websocket.js";

const smoke = __ENV.PROFILE === "smoke";

function scenario(exec, vus) {
  if (smoke) return { executor: "constant-vus", exec, vus, duration: "1m" };
  return {
    executor: "ramping-vus",
    exec,
    startVUs: 0,
    stages: [
      { duration: "2m", target: vus },
      { duration: "30m", target: vus },
    ],
  };
}

export const options = {
  scenarios: {
    portal_readers: scenario("browseScenario", smoke ? 4 : 180),
    messenger_users: scenario("messengerScenario", smoke ? 2 : 90),
    active_realtime: scenario("realtimeScenario", smoke ? 2 : 30),
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
