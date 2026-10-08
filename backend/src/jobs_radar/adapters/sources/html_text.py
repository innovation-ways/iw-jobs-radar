"""Reduce a job description to safe plain text (document 13, section 5.1).

Greenhouse returns the description as HTML that is itself entity-escaped (``&lt;div&gt;``). The
text is decoded once, sanitised with an allow-list (scripts, styles, frames, forms, images,
tracking pixels and every attribute are dropped) and converted to lines. Only the text is ever
stored or shown: the original HTML is never rendered.
"""

import html
import re

import nh3
from bs4 import BeautifulSoup, Tag

_ALLOWED_TAGS = {
    "p", "br", "div", "span", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "table", "thead", "tbody", "tr", "td", "th", "blockquote",
}  # fmt: skip
_PARAGRAPH_TAGS = (
    "p",
    "div",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "blockquote",
)


def _structure(soup: BeautifulSoup) -> None:
    """Insert line breaks so block elements become lines; list items get a ``- `` prefix."""
    for tag in soup.find_all("br"):
        tag.replace_with("\n")
    for tag in soup.find_all("li"):
        if isinstance(tag, Tag):
            tag.insert(0, "- ")
            tag.append("\n")
    for tag in soup.find_all(["tr"]):
        if isinstance(tag, Tag):
            tag.append("\n")
    for tag in soup.find_all(list(_PARAGRAPH_TAGS)):
        if isinstance(tag, Tag):
            tag.insert(0, "\n")
            tag.append("\n")


def html_to_text(escaped_html: str | None) -> str:
    """Return the readable text of an entity-escaped HTML description (``""`` when empty)."""
    if not escaped_html:
        return ""
    markup = html.unescape(escaped_html)
    cleaned = nh3.clean(markup, tags=_ALLOWED_TAGS, attributes={}, link_rel=None)
    soup = BeautifulSoup(cleaned, "lxml")
    _structure(soup)
    lines = [" ".join(line.split()) for line in soup.get_text().splitlines()]
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)
