"""HTTP client for the interface API.

Wraps requests.Session with base-URL joining, a default timeout and logging
that masks passwords and tokens so reports are safe to share.
"""

import json
import logging

import requests

from utility.api import api_config

logger = logging.getLogger("api")

MASKED = "***"
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}
SENSITIVE_FIELDS = {"password", "access_token", "refresh_token"}
MAX_LOGGED_BODY = 800


def _mask(value):
    if isinstance(value, dict):
        return {
            k: (MASKED if k.lower() in SENSITIVE_FIELDS else _mask(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask(item) for item in value]
    return value


def _truncate(text):
    if len(text) <= MAX_LOGGED_BODY:
        return text
    return f"{text[:MAX_LOGGED_BODY]}... [+{len(text) - MAX_LOGGED_BODY} chars]"


def body_text(response):
    """Response body as text, with secrets masked."""
    try:
        return json.dumps(_mask(response.json()))
    except ValueError:
        return response.text


class APIClient:
    def __init__(self, base_url=None, timeout=None, origin=None):
        self.base_url = (base_url or api_config.BASE_URL).rstrip("/")
        self.timeout = timeout or api_config.REQUEST_TIMEOUT
        origin = origin or api_config.ORIGIN
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": origin,
                "Referer": f"{origin}/",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
                ),
            }
        )

    def set_token(self, token):
        """Attach a bearer token, or pass None to drop it."""
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers.pop("Authorization", None)
        return self

    def _url(self, path):
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def request(self, method, path, **kwargs):
        url = self._url(path)
        kwargs.setdefault("timeout", self.timeout)

        logger.info("--> %s %s", method.upper(), url)
        if kwargs.get("json") is not None:
            logger.info("    body: %s", _truncate(json.dumps(_mask(kwargs["json"]))))

        response = self.session.request(method, url, **kwargs)

        logger.info(
            "<-- %s (%.0f ms) %s",
            response.status_code,
            response.elapsed.total_seconds() * 1000,
            _truncate(body_text(response)),
        )
        return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
