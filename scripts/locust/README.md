# Locust Load Tests – LLM Endpoints

Two user classes in `locustfile.py`:

| Class | Tag | Description |
|---|---|---|
| `DirectLLMUser` | `direct` | Hits an LLM / OpenAI-compatible endpoint directly (no auth) |
| `FDJWTUser` | `fd_jwt` | Routes through the Front Door; fetches a JWT every 15 min |

---

## Install

```bash
pip install locust>=2.20.0
# or from the project root:
pip install -r requirements.txt
```

---

## Configuration

All settings are controlled by environment variables. Copy and edit as needed:

### Direct LLM

| Variable | Default | Description |
|---|---|---|
| `DIRECT_LLM_URL` | `http://localhost:8000` | Base URL of the LLM service |
| `DIRECT_LLM_PATH` | `/v1/chat/completions` | Chat completions path |
| `DIRECT_LLM_MODEL` | `meta/llama-3.3-70b-instruct` | Model name |
| `DIRECT_LLM_API_KEY` | _(empty)_ | Bearer API key if required |

### Front Door + JWT

| Variable | Default | Description |
|---|---|---|
| `FD_BASE_URL` | `http://localhost:8080` | Front Door base URL |
| `FD_PROJECT` | `myproject` | Project/route prefix (e.g. `sas2py`) |
| `FD_LLM_PATH` | `/v1/chat/completions` | LLM path under the project prefix |
| `JWT_AUTH_PATH` | `/token` | Auth endpoint path on FD_BASE_URL |
| `JWT_USERNAME` | `admin` | Username for the JWT auth endpoint |
| `JWT_PASSWORD` | `admin` | Password for the JWT auth endpoint |
| `JWT_REFRESH_SECONDS` | `900` | Token refresh interval (default 15 min) |
| `LLM_MODEL` | `meta/llama-3.3-70b-instruct` | Model name sent via FD |

> The full LLM path through FD is built as `/{FD_PROJECT}{FD_LLM_PATH}`.  
> Example: `FD_PROJECT=sas2py` + `FD_LLM_PATH=/v1/chat/completions` → `/sas2py/v1/chat/completions`

---

## Running

### Web UI (interactive)

```bash
cd scripts/locust
locust -f locustfile.py
# Open http://localhost:8089
```

### Headless – both user classes

```bash
locust -f locustfile.py --headless -u 10 -r 2 --run-time 2m \
  --host http://localhost:8080
```

### Headless – direct LLM only

```bash
locust -f locustfile.py --headless -u 10 -r 2 --run-time 2m \
  --tags direct \
  DIRECT_LLM_URL=http://my-llm-host:8000 \
  locust -f locustfile.py --headless -u 10 -r 2 --run-time 2m --tags direct
```

Or with env vars:

```bash
export DIRECT_LLM_URL=https://integrate.api.nvidia.com
export DIRECT_LLM_PATH=/v1/chat/completions
export DIRECT_LLM_MODEL=meta/llama-3.3-70b-instruct
export DIRECT_LLM_API_KEY=nvapi-xxxx

locust -f locustfile.py --headless -u 10 -r 2 --run-time 2m --tags direct
```

### Headless – Front Door + JWT only

```bash
export FD_BASE_URL=http://localhost:8080
export FD_PROJECT=sas2py
export JWT_AUTH_PATH=/token
export JWT_USERNAME=myuser
export JWT_PASSWORD=mypassword
export JWT_REFRESH_SECONDS=900

locust -f locustfile.py --headless -u 5 -r 1 --run-time 5m --tags fd_jwt
```

---

## Token Refresh Logic (`FDJWTUser`)

- On `on_start` an initial token is fetched before any task runs.
- Before each request the age of the cached token is checked against `JWT_REFRESH_SECONDS`.
- If the token has expired (age ≥ threshold) it is refreshed synchronously before the LLM call.
- A `401` response from the LLM endpoint forces an immediate refresh on the next request.
- Token refresh requests appear in Locust stats under the name `jwt /token (refresh)`.
# Quick Start
# Direct LLM
export DIRECT_LLM_URL=https://integrate.api.nvidia.com
export DIRECT_LLM_API_KEY=nvapi-xxxx
locust -f scripts/locust/locustfile.py --headless -u 10 -r 2 --run-time 2m --tags direct

# Via Front Door with JWT
export FD_BASE_URL=http://localhost:8080
export FD_PROJECT=sas2py
export JWT_USERNAME=myuser
export JWT_PASSWORD=mypassword
locust -f scripts/locust/locustfile.py --headless -u 5 -r 1 --run-time 5m --tags fd_jwt