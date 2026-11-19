"""Constants for the ДонТел Личный кабинет integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "dontel_cabinet"

# The ISP cabinet is a WordPress site; its "carbon-billing" plugin serves both
# the cabinet page and the IP-based auto-login endpoint used by its own JS.
CABINET_PATH = "/cabinet/welcome/"
LOGIN_PATH = "/wp-content/plugins/carbon-billing/ajax_login.php"

DEFAULT_URL = "http://10.90.1.27/cabinet/welcome/"

# The account balance is in Russian rubles.
CURRENCY = "RUB"

# The balance changes slowly; hourly polling as requested.
DEFAULT_UPDATE_INTERVAL = timedelta(hours=1)

# The cabinet is known to answer very slowly; keep a generous request budget.
DEFAULT_TIMEOUT = 60.0
# The auto-login POST is cheap; do not let it eat the whole page budget.
LOGIN_TIMEOUT = 20.0

# The cabinet auto-logs-in by client IP. A browser UA keeps the requests
# indistinguishable from the user's own browsing of the same page.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"
