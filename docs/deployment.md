# Deployment

The application works entirely locally. No cloud deployment is required to demonstrate it, and no cloud service is provisioned by running setup.

## Render option

`render.yaml` is a prepared single-service configuration. It uses one Python process to serve the interface and simulation API together. A separate Vercel frontend is unnecessary for this version. The configuration selects the free plan and disables automatic deployments. Review the service plan and terms in your own account before creating it.

Import this repository as a Render Blueprint, review the proposed service and deploy. The entry point reads Render's `PORT` environment variable and binds to `HOST=0.0.0.0`. Health endpoint: `/healthz`. A private GitHub repository requires the existing Render GitHub integration to have access; this project does not grant that integration or store a token.

This prepared configuration has not itself established a live deployment. Verify the returned public URL and run the demonstration before sending a link to a recruiter. Free services may sleep and take time to wake; check current [Render documentation](https://render.com/docs/free).

## Container option

```bash
docker build -t waterjet-control-lab .
docker run --rm -p 127.0.0.1:8787:8787 waterjet-control-lab
```

The Dockerfile runs the web app without root privileges. It excludes Qt because a web deployment does not need a native desktop window. A running Docker engine is required for these commands. The container build is a prepared option; do not count it as verified until it has actually been built and health-checked.

## Public demonstration limits

- One process/one worker, no horizontal scaling: sessions live in memory and are lost on restart.
- 64 simultaneous sessions; expiration after 30 minutes of inactivity. Reload creates a new anonymous session.
- Temporary random session IDs are not user accounts or durable authentication. No private documents, real equipment or personal records belong in this demo.
- No external APIs, analytics, third-party fonts, credentials or paid model calls.
- Simulation time is advanced by requests. A browser disconnection does not exercise a real-time hardware watchdog.
- Production load testing, durable storage, accounts, distributed rate limiting and operational monitoring are outside the scope of this portfolio service.

Avoid adding secrets to the repository or using this adapter for real control hardware.
