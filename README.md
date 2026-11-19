# ДонТел Личный кабинет (custom component)

Home Assistant integration that reads the **Баланс** value from the ДонТел
(carbon-billing) personal cabinet page `http://10.90.1.27/cabinet/welcome/`
and exposes it as a numeric money sensor (`sensor.dontel_lichnyi_kabinet_balance`,
unit RUB), refreshed every hour.

## How it works

- The cabinet logs visitors in **by IP address**: the page itself POSTs
  `auto_login=1` to `/wp-content/plugins/carbon-billing/ajax_login.php` to
  start a PHP session for the requesting IP. This integration performs the
  same request (no username/password is stored anywhere), then keeps the
  `PHPSESSID` cookie for subsequent fetches.
  This is also why a plain `curl` of the page looks unauthenticated — the
  HTML served on first hit always contains only the auto-login script; the
  table appears once the session cookie is set.
- The balance row (`Баланс` / `2 589,09`) is parsed out of the "Лицевой счет"
  table and converted to a float (`2589.09`).
- The page is known to be slow: each request gets a 60 s budget.
- If the cabinet page merely fails or times out, the sensor keeps showing
  the last known balance. If the cabinet stops recognizing the Home Assistant
  host's IP, the entry raises a **reauthentication** notification; opening it
  retries the IP login.
- Polling interval: 1 hour (fixed in `const.py`, `DEFAULT_UPDATE_INTERVAL`).

## Install

1. Copy `custom_components/dontel_cabinet/` into
   `<config>/custom_components/dontel_cabinet/`.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **ДонТел Личный кабинет**.
   The default URL `http://10.90.1.27/cabinet/welcome/` is pre-filled.
4. The flow validates reachability + auto-login before creating the entry.

No third-party Python requirements; parsing is regex-based on the fetched HTML.

## Notes

- Works only while the HA host's IP is the one the ISP associates with the
  account (same as the browser experience). After a WAN IP change, expect the
  reauth notification; confirm it once the cabinet accepts the new IP again.
- The integration sends a normal browser User-Agent so the cabinet treats it
  like the subscriber's own browsing.
- One integration instance is allowed (the cabinet identifies the client by
  IP, so a second entry would show the same account).

## Tests

The test suite runs the integration against a fake aiohttp implementation of
the cabinet (auto-login + cookie sessions, verbatim page fragments):

```
. .venv-ha/bin/activate        # HA 2026.11 + pytest-homeassistant-custom-component
python -m pytest custom_components/dontel_cabinet/tests/ -q
```
