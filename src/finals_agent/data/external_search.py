from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from finals_agent.core.exceptions import ExternalSearchError, ToolInputError


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass(frozen=True)
class ExternalPaper:
    title: str
    authors: tuple[str, ...]
    summary: str
    url: str
    published: str | None = None
    categories: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "summary": self.summary,
            "url": self.url,
            "published": self.published,
            "categories": list(self.categories),
        }


class ArxivPaperSearch:
    def search(self, query: str, limit: int = 5) -> tuple[ExternalPaper, ...]:
        if not query.strip():
            raise ToolInputError("query cannot be empty.")
        if len(query) > 256:
            raise ToolInputError("arXiv query must be 256 characters or fewer.")
        if limit < 1:
            return ()
        safe_limit = max(1, min(limit, 20))
        params = urllib.parse.urlencode(
            {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": safe_limit,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        request = urllib.request.Request(
            f"{ARXIV_API_URL}?{params}",
            headers={"User-Agent": "paper-agent/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = response.read()

            root = ET.fromstring(payload)
        except (OSError, TimeoutError, urllib.error.URLError, ET.ParseError) as exc:
            raise ExternalSearchError(f"arXiv search failed for query '{query}'.") from exc
        papers = []
        for entry in root.findall("atom:entry", ATOM_NS):
            papers.append(_parse_entry(entry))
        return tuple(papers)


def _parse_entry(entry: ET.Element) -> ExternalPaper:
    title = _clean_text(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
    summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
    published = entry.findtext("atom:published", default="", namespaces=ATOM_NS) or None
    if published:
        published = _normalize_date(published)
    authors = tuple(
        _clean_text(author.findtext("atom:name", default="", namespaces=ATOM_NS))
        for author in entry.findall("atom:author", ATOM_NS)
    )
    url = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
    categories = tuple(
        category.attrib.get("term", "")
        for category in entry.findall("atom:category", ATOM_NS)
        if category.attrib.get("term")
    )
    return ExternalPaper(
        title=title,
        authors=tuple(author for author in authors if author),
        summary=summary,
        url=url,
        published=published,
        categories=categories,
    )


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _normalize_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value
