"""Fixtures emulating the carbon-billing cabinet."""

from __future__ import annotations

import pytest

# Verbatim structure of http://10.90.1.27/cabinet/welcome/ when logged in.
AUTHED_PAGE = """<!doctype html><html lang="ru-RU"><head><meta charset="utf-8">
<title>  Лицевой счет  |  ДонТел</title></head><body>
<div class='cabinet-module carbon_modules_abonentaccount'><table class="table table-bordered">
    <tr>
        <td class="col-md-6">ФИО</td>
        <td>Иванов Иван Иванович</td>
    </tr>
    <tr>
        <td>Логин</td>
        <td><strong>9050000000</strong></td>
    </tr>
    <tr>
        <td>Баланс</td>
        <td>2 589,09</td>
    </tr>
    <tr>
        <td>Хватит денег до</td>
        <td>28.12.2026</td>
    </tr>
</table>
</div></body></html>"""

# What a cookie-less request gets back: the auto-login form, no table.
LOGIN_PAGE = """<!doctype html><html lang="ru-RU"><body>
<div class='cabinet-module carbon_modules_authorize'>
<form role="form" action="/cabinet/welcome/" method="post">
<div id="login-preloader"><i class="fa fa-spinner fa-spin"></i></div>
</form>
<script>
    $.post('/wp-content/plugins/carbon-billing/ajax_login.php', {auto_login: 1}, function(result){
        if (result && result.logged){ location.reload(); }
    }, 'json');
</script></div></body></html>"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in every test."""
    yield


@pytest.fixture(autouse=True)
def auto_enable_socket(socket_enabled):
    """Allow real loopback sockets for the fake cabinet server."""
    yield
