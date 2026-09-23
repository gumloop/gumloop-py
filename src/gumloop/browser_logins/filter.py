"""Which cookies belong to the site a URL names."""

from __future__ import annotations

from urllib.parse import urlsplit

# Second-level public suffixes common enough that "last two labels" would be wrong.
_TWO_LABEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "me.uk",
    "ltd.uk",
    "net.uk",
    "com.au",
    "net.au",
    "org.au",
    "edu.au",
    "gov.au",
    "co.nz",
    "org.nz",
    "net.nz",
    "govt.nz",
    "co.jp",
    "ne.jp",
    "or.jp",
    "ac.jp",
    "go.jp",
    "com.br",
    "net.br",
    "org.br",
    "gov.br",
    "co.in",
    "net.in",
    "org.in",
    "gov.in",
    "ac.in",
    "co.za",
    "org.za",
    "net.za",
    "gov.za",
    "com.mx",
    "com.ar",
    "com.sg",
    "com.hk",
    "com.tw",
    "com.tr",
    "com.cn",
    "com.my",
    "com.ph",
    "co.kr",
    "or.kr",
    "co.il",
    "co.id",
    "co.th",
    "com.co",
    "com.pe",
    "com.ve",
    "com.ec",
    "com.uy",
}


def registrable_domain(host: str) -> str:
    """``app.foo.co.uk`` -> ``foo.co.uk``; bare hosts (localhost, IPs) stay whole.

    The backend applies the full public suffix list; this only needs to be close enough that
    the cookies it keeps are a superset of what the backend accepts for the site.
    """
    host = (host or "").strip().lower().rstrip(".").lstrip(".")
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2 or all(label.isdigit() for label in labels):
        return ".".join(labels)
    if ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def site_of_url(url: str) -> str:
    parts = urlsplit(url if "://" in url else f"https://{url}")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Enter the site as an http(s) address, for example https://app.example.com")
    return registrable_domain(parts.hostname)


def cookie_belongs_to_site(domain: str, site: str) -> bool:
    domain = (domain or "").lower().lstrip(".")
    return bool(site) and (domain == site or domain.endswith("." + site))
