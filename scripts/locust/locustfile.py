"""
Locust load tests for LLM endpoints.

Two user classes:
  1. DirectLLMUser  – hits an LLM / OpenAI-compatible endpoint directly (no auth).
  2. FDJWTUser      – routes through the Front Door; refreshes a JWT every 15 minutes
                     and injects it as a Bearer token on every LLM request.

Configuration via environment variables (or edit the defaults below):

  # Direct LLM
  DIRECT_LLM_URL        Base URL of the LLM service  (default: http://localhost:8000)
  DIRECT_LLM_PATH       Path for chat completions     (default: /v1/chat/completions)
  DIRECT_LLM_MODEL      Model name to send            (default: meta/llama-3.3-70b-instruct)
  DIRECT_LLM_API_KEY    Bearer API key if required    (default: "")

  # Front Door + JWT
  FD_BASE_URL           Front Door base URL           (default: http://localhost:8080)
  FD_PROJECT            Project/route prefix          (default: myproject)
  FD_LLM_PATH           Path under project for LLM   (default: /v1/chat/completions)
  JWT_AUTH_PATH         Auth path under FD_BASE_URL   (default: /token)
  JWT_USERNAME          Username for token endpoint   (default: admin)
  JWT_PASSWORD          Password for token endpoint   (default: admin)
  JWT_REFRESH_SECONDS   How often to refresh token    (default: 900  = 15 min)
  LLM_MODEL             Model name sent via FD        (default: meta/llama-3.3-70b-instruct)

Run examples:
  locust -f locustfile.py --headless -u 10 -r 2 --run-time 2m
  locust -f locustfile.py --headless -u 5  -r 1 --run-time 2m --tags direct
  locust -f locustfile.py --headless -u 5  -r 1 --run-time 2m --tags fd_jwt
"""

import os
import time
import threading
import logging

from locust import HttpUser, task, between, tag, events

logger = logging.getLogger("locust.llm")

# ---------------------------------------------------------------------------
# Shared prompts – rotate through these to vary load
# ---------------------------------------------------------------------------
SAMPLE_PROMPTS = [
    "What is the capital of France?",
    "Explain the difference between supervised and unsupervised learning in two sentences.",
    "Write a one-line Python function that reverses a string.",
    "What are three benefits of containerising applications?",
    "Summarise the concept of retrieval-augmented generation (RAG) briefly.",
    "What is the time complexity of binary search?",
    "Give a short definition of a transformer neural network.",
    "List two common use-cases for Redis.",
]

_prompt_index = 0
_prompt_lock = threading.Lock()


def next_prompt() -> str:
    global _prompt_index
    with _prompt_lock:
        p = SAMPLE_PROMPTS[_prompt_index % len(SAMPLE_PROMPTS)]
        _prompt_index += 1
    return p


def _build_chat_body(model: str, prompt: str) -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise and helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 256,
        "temperature": 0.7,
        "stream": False,
    }


# ---------------------------------------------------------------------------
# 1. Direct LLM User
# ---------------------------------------------------------------------------
DIRECT_LLM_URL   = os.getenv("DIRECT_LLM_URL",   "http://localhost:8000")
DIRECT_LLM_PATH  = os.getenv("DIRECT_LLM_PATH",  "/v1/chat/completions")
DIRECT_LLM_MODEL = os.getenv("DIRECT_LLM_MODEL", "meta/llama-3.3-70b-instruct")
DIRECT_LLM_API_KEY = os.getenv("DIRECT_LLM_API_KEY", "")


class DirectLLMUser(HttpUser):
    """Sends chat-completion requests directly to an LLM endpoint."""

    host = DIRECT_LLM_URL
    wait_time = between(1, 3)

    def on_start(self):
        self._headers = {"Content-Type": "application/json"}
        if DIRECT_LLM_API_KEY:
            self._headers["Authorization"] = f"Bearer {DIRECT_LLM_API_KEY}"

    @tag("direct")
    @task
    def chat_completion(self):
        prompt = next_prompt()
        body = _build_chat_body(DIRECT_LLM_MODEL, prompt)
        with self.client.post(
            DIRECT_LLM_PATH,
            json=body,
            headers=self._headers,
            name="direct /v1/chat/completions",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices:
                        resp.success()
                    else:
                        resp.failure(f"No choices in response: {resp.text[:200]}")
                except Exception as exc:
                    resp.failure(f"JSON parse error: {exc}")
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")


# ---------------------------------------------------------------------------
# 2. Front Door + JWT User
# ---------------------------------------------------------------------------
FD_BASE_URL        = os.getenv("FD_BASE_URL",        "http://localhost:8080")
FD_PROJECT         = os.getenv("FD_PROJECT",         "myproject")
FD_LLM_PATH        = os.getenv("FD_LLM_PATH",        "/v1/chat/completions")
JWT_AUTH_PATH      = os.getenv("JWT_AUTH_PATH",      "/token")
JWT_USERNAME       = os.getenv("JWT_USERNAME",       "admin")
JWT_PASSWORD       = os.getenv("JWT_PASSWORD",       "admin")
JWT_REFRESH_SECS   = int(os.getenv("JWT_REFRESH_SECONDS", "900"))  # 15 minutes
LLM_MODEL          = os.getenv("LLM_MODEL",          "meta/llama-3.3-70b-instruct")

# Full LLM path through FD: /<project><llm_path>
FD_LLM_FULL_PATH = f"/{FD_PROJECT.strip('/')}{FD_LLM_PATH}"


class FDJWTUser(HttpUser):
    """
    Routes LLM requests through the Front Door.
    Obtains a JWT from the auth endpoint and refreshes it every JWT_REFRESH_SECS
    seconds (default 15 minutes) without blocking ongoing requests.
    """

    host = FD_BASE_URL
    wait_time = between(1, 3)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_start(self):
        self._token: str = ""
        self._token_acquired_at: float = 0.0
        self._token_lock = threading.Lock()
        # Fetch an initial token before the first task runs
        self._refresh_token()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def _refresh_token(self):
        """POST to the JWT auth endpoint and store the access token."""
        try:
            resp = self.client.post(
                JWT_AUTH_PATH,
                json={"username": JWT_USERNAME, "password": JWT_PASSWORD},
                name="jwt /token (refresh)",
                catch_response=True,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = (
                    data.get("access_token")
                    or data.get("token")
                    or data.get("jwt")
                    or ""
                )
                if token:
                    with self._token_lock:
                        self._token = token
                        self._token_acquired_at = time.monotonic()
                    resp.success()
                    logger.info("JWT token refreshed successfully")
                else:
                    resp.failure(f"Token field not found in response: {list(data.keys())}")
            else:
                resp.failure(f"Auth failed HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            logger.error(f"Token refresh error: {exc}")

    def _get_token(self) -> str:
        """Return the current token, refreshing if it is older than JWT_REFRESH_SECS."""
        age = time.monotonic() - self._token_acquired_at
        if age >= JWT_REFRESH_SECS:
            self._refresh_token()
        with self._token_lock:
            return self._token

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    @tag("fd_jwt")
    @task
    def chat_completion_via_fd(self):
        token = self._get_token()
        if not token:
            logger.warning("Skipping task – no JWT token available")
            return

        prompt = next_prompt()
        body = _build_chat_body(LLM_MODEL, prompt)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        with self.client.post(
            FD_LLM_FULL_PATH,
            json=body,
            headers=headers,
            name=f"fd_jwt /{FD_PROJECT}{FD_LLM_PATH}",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices:
                        resp.success()
                    else:
                        resp.failure(f"No choices in response: {resp.text[:200]}")
                except Exception as exc:
                    resp.failure(f"JSON parse error: {exc}")
            elif resp.status_code == 401:
                # Token may have been invalidated server-side; force refresh
                logger.warning("401 received – forcing token refresh")
                self._token_acquired_at = 0.0
                resp.failure("401 Unauthorized – token refreshed for next request")
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
