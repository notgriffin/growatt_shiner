# Growatt Shiner — Home Assistant integration

[![Validate](https://github.com/notgriffin/growatt_shiner/actions/workflows/validate.yml/badge.svg)](https://github.com/notgriffin/growatt_shiner/actions/workflows/validate.yml)
[![Tests](https://github.com/notgriffin/growatt_shiner/actions/workflows/test.yml/badge.svg)](https://github.com/notgriffin/growatt_shiner/actions/workflows/test.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Monitor a Growatt inverter through Growatt's new **Shiner** cloud
(`shiner-us.growatt.com`), the backend that replaced the old
`server.growatt.com` API for migrated US accounts. It re-implements the
monitoring side of the original `growatt_server` integration and adds the
battery / hybrid data the new API exposes — read-only, no control entities.

Verified against a **MIN 8.2‑11.4KTL‑XH‑US** hybrid inverter.

## Features

- One Home Assistant **device per inverter**, discovered automatically from the
  account (serial, model, plant name, firmware).
- Live sensors from the inverter flow diagram: PV power and per‑string
  voltage/current/power, AC output, load, grid voltage/current/frequency, power
  factor, battery SOC and charge/discharge power, and energy today/total for
  solar, grid, load and battery.
- Inverter temperature, P‑bus voltage and rated power (diagnostic).
- An **Online** connectivity binary sensor per inverter.
- All cumulative energy sensors are `total_increasing`, so they work in the HA
  Energy dashboard.

Voltage, current, frequency, power‑factor and rated‑power entities are created
disabled by default — enable them per inverter if you want them.

## Installation

**HACS (custom repository):** in HACS, open **⋮ → Custom repositories**, add
`https://github.com/notgriffin/growatt_shiner` with type *Integration*, install
**Growatt Shiner**, and restart Home Assistant.

**Manual:** copy `custom_components/growatt_shiner/` into your HA
`config/custom_components/` directory and restart.

## Setup

**Settings → Devices & Services → Add Integration → Growatt Shiner.**

1. Enter your Shiner **username**, **password**, and region.
2. Type the **captcha** shown on the next screen (the image is displayed in the
   form).

That's it. Because the site requires a captcha, login happens once at setup; the
integration then keeps a long‑lived session and refreshes it silently. If the
session ever expires (~30 days), Home Assistant prompts you to re‑enter your
password and captcha via its normal re‑authentication flow.

The **update interval** (default 60 s) is configurable under the integration's
options.

### Unattended re‑authentication (AI captcha)

To avoid ever touching a captcha again, the integration can solve it
automatically when the session expires, using Home Assistant's built‑in
[AI Task](https://www.home-assistant.io/integrations/ai_task/). Pick any AI Task
entity (OpenAI, Anthropic, Google, local Ollama, …) — one that supports image
input — in the **AI Task entity** field at setup or under the integration's
options. Leave it blank to use your default AI Task entity, or to keep entering
captchas manually.

When enabled, an expired session triggers a silent re‑login: the integration
fetches a fresh captcha, asks the AI Task entity to read the four digits, and
logs back in with no user interaction. If the AI is unavailable or misreads
after a few tries, it falls back to the normal manual re‑authentication prompt.

**Note:** this build stores your Growatt **password** in Home Assistant's
config‑entry storage so it can re‑authenticate on its own when the session
expires — the unattended behaviour this integration is built for. It's redacted
from diagnostics, and most cloud integrations store credentials the same way. If
no AI Task entity is available when the session expires, it simply falls back to
Home Assistant's normal manual re‑authentication prompt.

## How it works

The Shiner web API is undocumented; this integration talks to it directly. The
login handshake, password hashing (`sha1(loginKey + sha1(password))`), the
`us_authorize` value (AES‑128‑CTR of the password) and the silent
access‑token refresh (via the `refresh-token` cookie) are all implemented in
[`shiner_api.py`](custom_components/growatt_shiner/shiner_api.py), which is
documented inline. The refresh token and your password (for unattended
re‑authentication, see above) are stored in Home Assistant's config‑entry
storage; nothing leaves your Home Assistant instance except the calls to the
Growatt API and — only if you opt into AI captcha solving — the captcha image
sent to your chosen AI Task entity.

## Testing

```bash
pip install -r requirements-test.txt
pytest
```

The suite (config flow, setup/unload, reauth, entity state) runs against a real
Home Assistant via `pytest-homeassistant-custom-component`.

## Disclaimer

Unofficial; not affiliated with or endorsed by Growatt. It relies on a private
API that Growatt may change at any time.
