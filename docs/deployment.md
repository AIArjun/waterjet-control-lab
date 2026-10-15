# Deployment

The browser demo is deployed at **https://waterjet-control-lab.onrender.com/** on a free Render web service in Frankfurt. Local setup remains available and does not provision any cloud resources. The public repository is https://github.com/AIArjun/waterjet-control-lab.

The service uses Python 3.13.16, one process and `/healthz`. The health response includes the deployed Git commit so it can be compared with the repository. Automatic deployment is off: push changes, wait for verification, then manually deploy the desired commit in Render. This keeps documentation-only pushes from restarting visitors' simulations.

## Render option

`render.yaml` is a prepared single-service configuration. It uses one Python process to serve the interface and simulation API together. A separate Vercel frontend is unnecessary for this version. The configuration selects the free plan and disables automatic deployments. Review the service plan and terms in your own account before creating it.

Import this repository as a Render Blueprint, review the proposed service and deploy. The entry point reads Render's `PORT` environment variable and binds to `HOST=0.0.0.0`. Health endpoint: `/healthz`. A private GitHub repository requires the existing Render GitHub integration to have access; this project does not grant that integration or store a token.

The hosted application was first deployed on 15 October 2026. Free services may sleep and take time to wake; check current [Render documentation](https://render.com/docs/free). Open the link shortly before a demonstration to allow for startup. No external keep-alive service has been added.

## Container option

```bash
docker build -t waterjet-control-lab .
docker run --rm -p 127.0.0.1:8787:8787 waterjet-control-lab
```

The Dockerfile runs the web app without root privileges. It excludes Qt because a web deployment does not need a native desktop window. A running Docker engine is required for these commands. The container build is a prepared option; do not count it as verified until it has actually been built and health-checked.

## Public demonstration limits

- One process/one worker, no horizontal scaling: sessions live in memory and are lost on restart.
- If a previous session no longer exists, the console stops sending ticks and offers **Restart**. Restart opens a fresh Disarmed simulation with neutral controls; it does not restore motion.
- 16 simultaneous sessions; expiration after 30 minutes of inactivity. This bound leaves memory headroom for the 512 MB free instance. Reload creates a new anonymous session.
- Temporary random session IDs are not user accounts or durable authentication. No private documents, real equipment or personal records belong in this demo.
- No external APIs, analytics, third-party fonts, credentials or paid model calls.
- Simulation time is advanced by requests. A browser disconnection does not exercise a real-time hardware watchdog.
- Production load testing, durable storage, accounts, distributed rate limiting and operational monitoring are outside the scope of this portfolio service.

Avoid adding secrets to the repository or using this adapter for real control hardware.
