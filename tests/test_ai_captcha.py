"""Tests for AI captcha solving via Home Assistant's ai_task integration."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.growatt_shiner.ai_captcha import async_solve_captcha

_DATA_URI = "data:image/png;base64,AAAA"


def _stub_ai_task(*, data=None, error=None) -> ModuleType:
    """A stand-in for homeassistant.components.ai_task to avoid its deps."""
    module = ModuleType("homeassistant.components.ai_task")
    module.async_generate_data = AsyncMock(
        return_value=SimpleNamespace(data=data), side_effect=error
    )
    return module


async def test_returns_none_when_ai_task_not_loaded(hass: HomeAssistant) -> None:
    """With no ai_task set up, solving is skipped (caller falls back to manual)."""
    assert await async_solve_captcha(hass, _DATA_URI) is None


async def test_parses_four_digits(hass: HomeAssistant) -> None:
    """A well-formed AI response yields the four digits."""
    hass.config.components.add("ai_task")
    stub = _stub_ai_task(data={"code": "0139"})
    with patch.dict(sys.modules, {"homeassistant.components.ai_task": stub}):
        code = await async_solve_captcha(hass, _DATA_URI, "ai_task.assistant")
    assert code == "0139"
    # The captcha image is passed as an attachment.
    kwargs = stub.async_generate_data.await_args.kwargs
    assert kwargs["attachments"][0]["media_content_type"] == "image/png"
    assert kwargs["entity_id"] == "ai_task.assistant"


async def test_ai_error_returns_none(hass: HomeAssistant) -> None:
    """An AI Task error (e.g. no entity configured) degrades gracefully."""
    hass.config.components.add("ai_task")
    stub = _stub_ai_task(error=HomeAssistantError("no entity"))
    with patch.dict(sys.modules, {"homeassistant.components.ai_task": stub}):
        assert await async_solve_captcha(hass, _DATA_URI, None) is None
