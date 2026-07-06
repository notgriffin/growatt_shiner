"""Solve the Shiner login captcha with Home Assistant's AI Task integration.

The Shiner login requires a 4-digit image captcha. This module hands that image
to whatever LLM the user has configured as an AI Task entity (OpenAI, Anthropic,
Google, local Ollama, ...) and returns the digits, so re-authentication can run
unattended when the ~30-day session expires.

AI Task attachments must resolve through a media source, so the captcha PNG is
written to ``<config>/media/growatt_shiner/`` (the default ``local`` media dir)
for the duration of the call and removed afterwards.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

_MEDIA_SUBDIR = "growatt_shiner"
_CAPTCHA_FILE = "captcha.png"
_MEDIA_CONTENT_ID = f"media-source://media_source/local/{_MEDIA_SUBDIR}/{_CAPTCHA_FILE}"
_STRUCTURE = vol.Schema({vol.Required("code"): str})
_INSTRUCTIONS = (
    "The attached image is a 4-digit numeric captcha from a login page. "
    "Read the four digits and respond with only those digits — no spaces, "
    "letters, or other text."
)


def _decode(image: str) -> bytes | None:
    """Decode a ``data:image/...;base64,...`` URI (or bare base64) to bytes."""
    payload = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        return base64.b64decode(payload)
    except (binascii.Error, ValueError):
        return None


async def async_solve_captcha(
    hass: HomeAssistant, image: str, entity_id: str | None = None
) -> str | None:
    """Return the captcha digits via AI Task, or ``None`` if unavailable/unreadable.

    ``None`` (rather than an exception) signals the caller to fall back to a
    manual captcha entry — AI solving is a best-effort convenience.
    """
    if "ai_task" not in hass.config.components:
        _LOGGER.debug("ai_task not set up; cannot auto-solve captcha")
        return None

    data = _decode(image)
    if not data:
        return None

    # ai_task is a soft dependency; import lazily so setup works without it.
    from homeassistant.components import ai_task

    media_dir = hass.config.path("media", _MEDIA_SUBDIR)
    path = os.path.join(media_dir, _CAPTCHA_FILE)

    def _write() -> None:
        os.makedirs(media_dir, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)

    def _cleanup() -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    await hass.async_add_executor_job(_write)
    try:
        result = await ai_task.async_generate_data(
            hass,
            task_name="Growatt Shiner captcha",
            entity_id=entity_id,
            instructions=_INSTRUCTIONS,
            structure=_STRUCTURE,
            attachments=[
                {
                    "media_content_id": _MEDIA_CONTENT_ID,
                    "media_content_type": "image/png",
                }
            ],
        )
    except HomeAssistantError as err:
        _LOGGER.warning("AI captcha solving failed: %s", err)
        return None
    finally:
        await hass.async_add_executor_job(_cleanup)

    code = str((result.data or {}).get("code", ""))
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 4:
        _LOGGER.debug("AI returned an unexpected captcha value: %r", code)
        return digits or None
    return digits
