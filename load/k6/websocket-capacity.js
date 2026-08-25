import { realtime } from './websocket.js';

export const options = {
  scenarios: {
    messenger_sockets: {
      executor: 'per-vu-iterations',
      vus: 300,
      iterations: 1,
      maxDuration: '16m',
    },
  },
  thresholds: {
    ws_connecting: ['p(95)<2000'],
    ws_session_duration: ['p(95)>895000'],
    tandem_realtime_failures: ['rate<0.01'],
  },
};

export default function () {
  realtime(900000, false);
}
