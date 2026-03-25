"""Deutsche Welle (DW) English RSS source configuration.

DW is Germany's international broadcaster. Their World News RSS feed
provides English-language coverage with strong focus on European politics,
African affairs, and developing-world topics — perspectives not well
covered by BBC, Swissinfo, or Al Jazeera.

Feed format: RSS 1.0 (RDF). feedparser handles this transparently — the
only difference from RSS 2.0 is the XML namespace, which feedparser
abstracts away.

One quirk: DW appends ``?maca=en-rss-en-world-4025-rdf`` (a campaign
tracking parameter) to every article URL.  We strip it so that stored
URLs are canonical and deduplication works correctly.
"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

SOURCE_NAME = "dw_world"
FEED_URL = "https://rss.dw.com/rdf/rss-en-world"


def clean_url(url: str) -> str:
    """Remove the ``maca`` tracking parameter from a DW URL.

    DW's RSS feed appends ``?maca=en-rss-en-world-4025-rdf`` to every link.
    Stripping it gives us the canonical article URL.

    >>> clean_url("https://www.dw.com/en/some-article/a-12345?maca=en-rss-en-world-4025-rdf")
    'https://www.dw.com/en/some-article/a-12345'
    >>> clean_url("https://www.dw.com/en/some-article/a-12345")
    'https://www.dw.com/en/some-article/a-12345'
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("maca", None)
    clean_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))
