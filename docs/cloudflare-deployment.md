# Cloudflare deployment

This page is retained as a compatibility entry point. The current production procedure is [`stage10/deployment.md`](stage10/deployment.md); incident recovery is [`stage10/incident-response.md`](stage10/incident-response.md).

The approved topology uses the remotely managed named tunnel `tandem-tvs`. Its public hostname targets `http://frontend:80` inside the isolated `tunnel-edge` network. Cloudflare Access must challenge anonymous users before origin content.

Production always starts through `compose.yaml` plus `compose.prod.yaml` and an operator-owned
secret env file. The production overlay removes the development-only tunnel profile, so plain
production `up -d --wait` includes `cloudflared`; do not add a profile flag. It uses local Tandem
authentication, `PORTAL_ADAPTER=unavailable`, one-shot migrations and exact SHA-tagged images. The
old Stage 1 mock/passwordless instructions are no longer valid.

Never commit or log `CLOUDFLARE_TUNNEL_TOKEN`. Do not publish Nginx, Django, PostgreSQL or Redis as a direct Internet origin. Multiple `cloudflared` processes on the same physical host protect only against connector-process failure; host-level HA requires another failure domain and separate database/media availability design.
