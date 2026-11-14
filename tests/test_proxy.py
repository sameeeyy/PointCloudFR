"""Tests for QGIS proxy settings -> requests proxies."""
from unittest.mock import MagicMock, patch

URL = "https://data.geopf.fr/wfs/ows"


def _proxies(host="", user="", password="", no_proxy=(), excluded=()):
    from point_cloud_fr.utils import config

    proxy = MagicMock()
    proxy.hostName.return_value = host
    proxy.port.return_value = 3128
    proxy.user.return_value = user
    proxy.password.return_value = password
    with patch.object(config, "QgsNetworkAccessManager") as nam:
        nam.instance.return_value.fallbackProxy.return_value = proxy
        nam.instance.return_value.noProxyList.return_value = list(no_proxy)
        nam.instance.return_value.excludeList.return_value = list(excluded)
        return config.get_qgis_proxies(URL)


def test_no_proxy_configured_uses_requests_defaults():
    assert _proxies() is None


def test_http_proxy_with_escaped_credentials():
    url = "http://bob:p%40ss%3A1@proxy.corp:3128"
    assert _proxies("proxy.corp", "bob", "p@ss:1") == {"http": url, "https": url}


def test_proxy_without_credentials():
    assert _proxies("proxy.corp")["https"] == "http://proxy.corp:3128"


def test_excluded_url_falls_back_to_system_proxy():
    assert _proxies("proxy.corp", excluded=["", "https://data.geopf.fr"]) is None


def test_no_proxy_url_bypasses_every_proxy():
    assert _proxies("proxy.corp", no_proxy=["https://data.geopf.fr"]) == {
        "http": "",
        "https": "",
    }
