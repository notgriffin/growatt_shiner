"""Async client for the Growatt Shiner web API (shiner-us.growatt.com).

This is a bespoke client for Growatt's new "Shiner" backend. There is no public
SDK; the login handshake and session model below were reverse-engineered from
the official web app and are documented inline so they can be re-verified.

Login handshake (all under ``<host>/web``):

1. ``GET  /v1/auth/login``   -> ``{"key": <loginKey>}`` (password salt)
2. ``POST /v1/auth/captcha`` -> ``{"b64": <png data-uri>}`` + ``Captcha`` cookie
3. ``POST /v1/auth/login``   with the body built in :meth:`ShinerApiClient.async_login`
   -> ``{"accessToken": <jwt>, "user": {...}}`` + ``refresh-token`` cookie

Session model: send ``Authorization: Bearer <accessToken>`` **and**
``Cookie: refresh-token=<jwt>`` on every request. The access token lives ~15 min;
when it expires the gateway mints a fresh one from the refresh cookie and returns
it in the response ``Authorization`` header (captured here). The refresh token
lives up to 30 days (``expire_minutes``), after which the user must log in again.
"""

from __future__ import annotations

import hashlib
import json as json_lib
import logging
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

# Literal key/IV embedded in the web app; us_authorize = hex(AES-128-CTR(password)).
_AES_KEY = b"VidaGrid&Growatt"
_AES_IV = b"Growatt&Password"

# 30 days, matching the app's "remember me" option, so the session is long-lived.
_EXPIRE_MINUTES = 43200

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class ShinerError(Exception):
    """A recoverable error talking to the Shiner API."""


class ShinerAuthError(ShinerError):
    """Authentication failed or the session expired (triggers reauth)."""


class ShinerCaptchaError(ShinerAuthError):
    """The captcha code was wrong; fetch a new captcha and retry."""


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()


def hash_password(password: str, login_key: str) -> str:
    """Return ``sha1(login_key + sha1(password))`` as lowercase hex."""
    return _sha1(login_key + _sha1(password))


def us_authorize(password: str) -> str:
    """Return ``hex(AES-128-CTR(password))`` with the app's fixed key/IV."""
    encryptor = Cipher(algorithms.AES(_AES_KEY), modes.CTR(_AES_IV)).encryptor()
    ciphertext = encryptor.update(password.encode()) + encryptor.finalize()
    return ciphertext.hex()


class ShinerApiClient:
    """Talks to one Shiner account. Reusable across the config flow and runtime."""

    def __init__(
        self,
        session: ClientSession,
        host: str,
        *,
        username: str | None = None,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ) -> None:
        """Initialize the client.

        For runtime use, pass the stored ``username`` and ``refresh_token``. The
        access token is optional; the gateway issues a fresh one on the first
        authenticated call using the refresh cookie.
        """
        self._session = session
        self._base = f"{host.rstrip('/')}/web"
        self.username = username
        self.refresh_token = refresh_token
        # A non-empty Bearer must be present for the refresh cookie to be honored.
        self.access_token = access_token or "init"
        self._login_key: str | None = None
        self._captcha_key: str | None = None
        # Handshake cookies (LoginKey, Captcha, refresh-token) accumulated here.
        self._cookies: dict[str, str] = {}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authed: bool = False,
    ) -> Any:
        """Send a request, track cookies/token rotation, and unwrap the envelope."""
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        if json is not None:
            headers["Content-Type"] = "application/json"
        cookies = dict(self._cookies)
        if authed:
            headers["Authorization"] = f"Bearer {self.access_token}"
            if self.refresh_token:
                cookies["refresh-token"] = self.refresh_token
        if cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

        try:
            async with self._session.request(
                method, self._base + path, json=json, headers=headers
            ) as resp:
                # Capture Set-Cookie (LoginKey, Captcha, refresh-token).
                for name, morsel in resp.cookies.items():
                    self._cookies[name] = morsel.value
                # Capture a silently-refreshed access token.
                new_auth = resp.headers.get("Authorization", "")
                if new_auth.lower().startswith("bearer "):
                    self.access_token = new_auth[7:].strip()
                status = resp.status
                text = await resp.text()
        except ClientError as err:
            raise ShinerError(f"Error communicating with Shiner: {err}") from err

        if status == 401:
            raise ShinerAuthError("Session expired or invalid credentials")

        try:
            payload: dict[str, Any] = json_lib.loads(text)
        except ValueError as err:
            raise ShinerError(f"Invalid response ({status}): {text[:200]}") from err

        code = payload.get("code")
        if code == 0:
            return payload.get("data")
        msg = str(payload.get("msg") or payload.get("data") or "")
        if code == 401 or "auth" in msg.lower():
            raise ShinerAuthError(msg or "Unauthorized")
        if "captcha" in msg.lower():
            raise ShinerCaptchaError(msg)
        raise ShinerError(f"Shiner API error {code}: {msg}")

    # -- Login handshake -----------------------------------------------------

    async def async_prepare_login(self) -> str:
        """Fetch the password salt + a captcha. Returns the captcha image data-URI."""
        data = await self._request("GET", "/v1/auth/login")
        self._login_key = (data or {}).get("key")
        if not self._login_key:
            raise ShinerError("Shiner did not return a login key")
        captcha = await self._request("POST", "/v1/auth/captcha", json={})
        self._captcha_key = self._cookies.get("Captcha")
        image = (captcha or {}).get("b64")
        if not image or not self._captcha_key:
            raise ShinerError("Shiner did not return a captcha")
        return image

    async def async_login(
        self, username: str, password: str, captcha: str
    ) -> dict[str, Any]:
        """Complete login. Requires a prior :meth:`async_prepare_login` call.

        On success, ``self.access_token`` / ``self.refresh_token`` are populated
        and the ``user`` object is returned.
        """
        if not self._login_key or not self._captcha_key:
            raise ShinerError("async_prepare_login must be called first")
        body = {
            "username": username,
            "password": hash_password(password, self._login_key),
            "captcha": captcha,
            "captchaKey": self._captcha_key,
            "us_authorize": us_authorize(password),
            "expire_minutes": _EXPIRE_MINUTES,
        }
        data = await self._request("POST", "/v1/auth/login", json=body)
        data = data or {}
        access = data.get("accessToken")
        refresh = self._cookies.get("refresh-token")
        if not access or not refresh:
            raise ShinerAuthError("Login did not return the expected tokens")
        self.username = username
        self.access_token = access
        self.refresh_token = refresh
        return data.get("user") or {}

    # -- Data ----------------------------------------------------------------

    async def async_get_inverters(self) -> list[dict[str, Any]]:
        """List the account's inverters with per-device metadata + a summary.

        Each row includes ``inverter_sn``, ``model``, ``plant``, ``is_online``,
        firmware ``version`` and today's ``ppv``/``eacToday``.
        """
        user = quote(self.username or "", safe="")
        path = f"/v1/inverters/1/100?query=&filter=&username={user}"
        data = await self._request("GET", path, authed=True)
        return (data or {}).get("list") or []

    async def async_get_diagram(self, serial: str) -> dict[str, Any]:
        """Return the live flow diagram for one inverter — the primary dataset.

        Flat JSON with live power (``pvPower``, ``pac``, ``loadPower``), per-string
        PV (``pv1Voltage``/``pv1Current``/``pv1Power`` ...), grid
        (``phaseRVoltage``, ``gridFreq``, ``powerFactor``), battery
        (``socBdc1``, ``chargePower``, ``dischargePower``) and energy today/total.
        """
        return (
            await self._request("GET", f"/v1/inverter/{serial}/diagram", authed=True)
            or {}
        )

    async def async_get_detail(self, serial: str) -> dict[str, Any]:
        """Return device parameters flattened to ``{by_address, by_name}``.

        The raw response is a display tree; :func:`flatten_detail` extracts each
        leaf keyed by its Modbus register address (stable) and display name.
        """
        tree = await self._request(
            "GET", f"/v1/inverter/{serial}?lang=en-us", authed=True
        )
        return flatten_detail(tree)


def flatten_detail(node: Any, out: dict[str, dict] | None = None) -> dict[str, dict]:
    """Recursively flatten the inverter-detail tree into address/name maps."""
    if out is None:
        out = {"by_address": {}, "by_name": {}}
    if isinstance(node, list):
        for item in node:
            flatten_detail(item, out)
    elif isinstance(node, dict):
        if "value" in node and "name" in node:
            out["by_name"][str(node["name"]).strip()] = node.get("value")
            address = node.get("address")
            if address is not None:
                out["by_address"][int(address)] = node.get("value")
        for child in node.get("children") or []:
            flatten_detail(child, out)
    return out
