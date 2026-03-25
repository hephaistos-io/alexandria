"""Al Jazeera English RSS source configuration.

Al Jazeera is a Qatar-based international news network. Their RSS feed
provides English-language coverage with a strong focus on Middle Eastern,
African, and Global South perspectives — complementing BBC (UK focus)
and Swissinfo (Swiss/European focus) already in the pipeline.

Feed format: Standard RSS 2.0 (WordPress-generated). Uses CDATA-wrapped
descriptions and RFC 2822 pubDates — all handled natively by feedparser.

One quirk: Al Jazeera appends ?traffic_source=rss to every article URL.
We strip this so that stored URLs are canonical and deduplication works
correctly if the same article appears via a different channel later.
"""

from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

SOURCE_NAME = "aljazeera"
FEED_URL = "https://www.aljazeera.com/xml/rss/all.xml"


def clean_url(url: str) -> str:
    """Remove the ``traffic_source`` tracking parameter from an Al Jazeera URL.

    Al Jazeera's RSS feed appends ``?traffic_source=rss`` to every link.
    Stripping it gives us the canonical article URL, which is better for
    deduplication (the same article reached via the website won't have
    that param) and cleaner for storage.

    >>> clean_url("https://www.aljazeera.com/news/2026/3/21/example?traffic_source=rss")
    'https://www.aljazeera.com/news/2026/3/21/example'
    >>> clean_url("https://www.aljazeera.com/news/2026/3/21/example")
    'https://www.aljazeera.com/news/2026/3/21/example'
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params.pop("traffic_source", None)
    # If no remaining params, query string becomes empty.
    clean_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=clean_query))
