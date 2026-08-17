# Security & Secrets

Censorarr can store credentials for optional integrations. Treat these values as secrets.

## Secret precedence

For supported secrets, Censorarr uses:

1. GUI-saved secret
2. environment variable
3. legacy config value

This matters when troubleshooting. A stale GUI-saved value can override an environment variable that appears correct.

## Secret storage

GUI-saved secrets are stored under the persistent `/config` area.

Do not expose, share, upload, or publish the contents of your runtime `/config` directory.

Sensitive data can include:

```text
secrets.json
config.yaml
.env files
API tokens
worker tokens
notification credentials
logs that contain private URLs or identifiers
backup snapshots containing configuration
```

## GPU Worker token

Use a long random value.

The exact same value must be configured on:

- the GPU Worker as `ASR_WORKER_TOKEN`
- the main Censorarr remote-GPU settings

Current protocol header:

```text
X-Censorarr-Token
```

Do not expose the real token in screenshots, support posts, logs, or configuration examples you share publicly.

## Web login

The shipped compose supports:

```yaml
WEB_USERNAME: "admin"
WEB_PASSWORD: ""
```

A blank password means no web login.

If Censorarr is exposed beyond a trusted LAN, use appropriate authentication, reverse-proxy, firewall, VPN, or other network controls rather than relying on an open application port.

## Keep the GPU Worker private

The worker accepts audio uploads for transcription. Keep TCP port `9000` on a trusted network or otherwise protect access, and always configure a worker token.

## Rotate leaked credentials

If a token or API key is accidentally exposed, treat it as compromised:

1. rotate or revoke it at the source
2. update Censorarr with the replacement value
3. remove the exposed value from any screenshots, posts, logs, or files you control
