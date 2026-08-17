# Updating Censorarr

## Normal source install

From the Censorarr project folder:

```bash
git pull
docker compose up -d --build
```

This updates source and recreates/rebuilds the container as needed.

## Synology Container Manager

After replacing/pulling source:

1. Open the Censorarr project.
2. Rebuild/recreate the project when Dockerfile, entrypoint, compose, or dependency behavior changed.
3. A simple restart is sufficient only for changes that are already bind-mounted into the running container and do not affect the image/entrypoint.

When in doubt after an application version update, rebuild.

## GPU Worker update

```bash
cd Censorarr/gpu-worker
git pull
docker compose down
docker compose up -d --build
```

If you use a separate clone on the GPU host, update that clone independently.

## Preserve these directories

Do not delete persistent runtime data unless you intentionally want a reset:

```text
config/
work/
gpu-worker/models/
```

## Before upgrading

Recommended:

- back up `/config`
- note your compose environment values
- confirm your worker token if using remote GPU
- keep a copy of custom profanity/exception files

## After upgrading

Check:

```bash
docker compose logs --tail=100
```

Run:

```bash
docker exec -it censorarr python /app/selftest.py
```

If the GPU Worker was also updated, test:

```bash
curl -H 'X-Censorarr-Token: YOUR_TOKEN' http://GPU-IP:9000/health
```
