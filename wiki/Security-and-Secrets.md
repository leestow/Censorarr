# Security & Secrets

Censorarr can store credentials for optional integrations. Treat these as secrets.

## Secret precedence

For supported secrets, Censorarr uses:

1. GUI-saved secret
2. environment variable
3. legacy config value

This matters when troubleshooting. A stale GUI-saved value can override an environment variable that appears correct.

## Secret storage

GUI-saved secrets are stored under the persistent `/config` area.

Do not publish runtime `/config` contents.

## Never commit

Avoid committing:

```text
config/
secrets.json
.env
.env.*
API tokens
worker tokens
logs
reports
model caches
backup snapshots containing config
```

The repository `.gitignore` excludes common runtime locations, but always review changes before pushing.

## GPU Worker token

Use a long random value.

The exact same value must be configured on:

- the GPU Worker as `ASR_WORKER_TOKEN`
- the main Censorarr remote-GPU settings

Current protocol header:

```text
X-Censorarr-Token
```

Do not publish the real token in screenshots, issues, logs, or your public compose file.

## Web login

The shipped compose supports:

```yaml
WEB_USERNAME: "admin"
WEB_PASSWORD: ""
```

A blank password means no web login.

If Censorarr is exposed beyond a trusted LAN, use appropriate authentication/reverse-proxy/network controls rather than relying on an open application port.

## Keep the GPU Worker private

The worker accepts audio uploads for transcription. Keep TCP 9000 on a trusted network or otherwise protect access, and always configure a worker token.

## Rotate leaked credentials

If a token/API key is accidentally committed to a public repository, treat it as compromised:

1. rotate/revoke it at the source
2. update Censorarr
3. remove it from current files
4. consider repository-history cleanup if necessary
