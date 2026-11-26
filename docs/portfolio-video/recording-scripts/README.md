# Recording scripts

`record.cjs` drives the real application with Playwright and captures clips R01–R15.
`encode.py` turns the captured frames into MP4 files. Run on 26 November 2026: all 15 clips
recorded.

**Needs:** Docker Desktop, Node 24 with the repository dependencies installed, Google Chrome,
Python with `opencv-python`, and Git Bash for the stack scripts.

## 1. Start a disposable stack (Git Bash, repository root)

```bash
export COMPOSE_PROJECT_NAME=acs-video-qa COMPOSE_ENV_FILES="$HOME/acs-video-qa.env"
bash scripts/ci/make-env.sh "$COMPOSE_ENV_FILES" 400
bash scripts/ci/up.sh web
```

`make-env.sh` writes synthetic credentials, the `demo` LLM, `hash` embeddings and empty provider
keys, and moves every port by the offset (web 3400, API 8400, mail 8425), away from your developer
stack. If Windows refuses a port, use another offset and adjust the URLs below.

## 2. Record and encode

```bash
WEB_URL=http://localhost:3400 API_URL=http://localhost:8400 MAILPIT_URL=http://127.0.0.1:8425 \
  node docs/portfolio-video/recording-scripts/record.cjs
python docs/portfolio-video/recording-scripts/encode.py output/video/portfolio
```

Output: `output/video/portfolio/` (`clips/`, `stills/`, `frames/`, `manifest.json`,
`tenant-isolation-statuses.txt`). It is gitignored. Each run replaces it.

## 3. Remove the stack

```bash
docker compose down -v
```

## Options

| Variable | Default | Meaning |
|---|---|---|
| `OUT_DIR` | `output/video/portfolio` | Where to write |
| `SCALE` | `1.25` | `2.5` requests 3840×2160. **Not tested**: check sharpness and smoothness before relying on it |
| `PUBLIC_SITE_URL` | empty | A public website **you own** to add as a source. Sends real requests to it. **Not tested** |
| `SHOP_PORT` | `3511` | Port of the fictional storefront and the widget test page |
| `E2E_BROWSER_CHANNEL` | `chrome` | Browser channel |

## Safety

The script refuses to run unless the named project's `api` and `worker` containers report
`LLM_PROVIDER=demo`, `EMBEDDING_PROVIDER=hash` and no provider key, and the URLs are that
project's ports. It never prints their values. Do not remove this check: your developer `.env`
holds real keys.

Each run signs up two new synthetic accounts. Sign-ups are rate limited per address; if a run
stops at sign-up after several attempts, recreate the disposable stack rather than changing any
limit. The script writes no password to disk.

## OBS alternative

If a script step fails or you prefer to drive by hand, follow the same actions from
[the checklist](../05_SCREEN_RECORDING_CHECKLIST.md) with the OBS settings in its section 3, on the
same disposable stack (verification mail is at the Mailpit address above).
