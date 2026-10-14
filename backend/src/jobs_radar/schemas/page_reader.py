"""The configuration of a careers-page reader the owner approved (ADR-070 layer 3).

A configuration is data, never code: CSS selectors that a fixed reader applies to a server-rendered
listing page. The local model may *propose* one and the owner reviews a preview before approving
it; later runs use it with no AI. It is versioned (``schema_version``) like the other JSON payloads.
"""

from typing import Annotated, Literal

from bs4 import BeautifulSoup
from pydantic import AfterValidator, Field

from jobs_radar.schemas.common import StrictModel

_PROBE = BeautifulSoup("<div></div>", "lxml")


def _selector(value: str) -> str:
    """Accept a CSS selector the reader's engine can compile."""
    text = value.strip()
    if not text:
        msg = "A selector cannot be blank."
        raise ValueError(msg)
    try:
        _PROBE.select(text)
    # The selector engine raises its own syntax error types; any failure means "not a selector".
    except Exception as error:
        msg = "That is not a valid CSS selector."
        raise ValueError(msg) from error
    return text


Selector = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_selector)]


class PageReaderConfig(StrictModel):
    """Where the postings are on a company's careers page and which parts mean what.

    ``item_selector`` matches each posting block of the listing page; the other selectors are
    relative to a block. Without ``link_selector`` the block's own address (or its first link) is
    the posting address. With ``fetch_detail`` each posting page is opened for its description.
    """

    schema_version: Literal[1] = 1
    listing_url: Annotated[str, Field(min_length=8, max_length=500)]
    item_selector: Selector
    title_selector: Selector | None = None
    link_selector: Selector | None = None
    location_selector: Selector | None = None
    description_selector: Selector | None = None
    next_page_selector: Selector | None = None
    fetch_detail: bool = True
    max_pages: Annotated[int, Field(ge=1, le=10)] = 3
