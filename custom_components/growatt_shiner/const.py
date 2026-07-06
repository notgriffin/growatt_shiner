"""Constants for the Growatt Shiner integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "growatt_shiner"

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

# Growatt's cloud only refreshes device data every few minutes; 60s polling is
# responsive without hammering the API.
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30

# Region hosts. The login screen the user was given is the US host; other
# regions expose the same /web API under their own hostname.
DEFAULT_HOST = "https://shiner-us.growatt.com"
HOSTS: dict[str, str] = {
    "United States": "https://shiner-us.growatt.com",
    "International": "https://shiner.growatt.com",
    "China": "https://shiner-cn.growatt.com",
}

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CAPTCHA = "captcha"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_ID = "user_id"
CONF_SCAN_INTERVAL = "scan_interval"
# Optional AI Task entity used to auto-solve the login captcha (unattended reauth).
CONF_AI_TASK_ENTITY = "ai_task_entity"
