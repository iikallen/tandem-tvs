# Cloudflare Tunnel deployment

The optional tunnel publishes only Nginx. PostgreSQL, Redis, and Django have no host ports. Public HTTPS terminates at Cloudflare; origin TLS is not required for this standalone development topology.

1. Create a remotely managed named tunnel and map its public hostname to `http://frontend:80`.
2. Put Cloudflare Access in front of the hostname with an explicit allow policy; do not use a public allow-all policy for employee data.
3. Supply `CLOUDFLARE_TUNNEL_TOKEN` through the deployment environment or secret store. Never add it to `.env.example`, Git, logs, or an image layer.
4. Start the isolated stack:

```sh
docker compose --profile tunnel up -d --build
```

For local access without a tunnel, use the explicit loopback-only override:

```sh
docker compose -f compose.yaml -f compose.local.yaml up -d --build
```

Then open `http://127.0.0.1:8080`. The production portal contract may require a different hostname, proxy chain, cookie policy, or Access topology; those decisions remain open in `portal-integration-questions.md`.
