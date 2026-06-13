from __future__ import annotations

from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from finals_agent.core.exceptions import ExternalSearchError, ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository, file_sha256


ARXIV_ID_RE = re.compile(
    r"^(?:abs|pdf)/(?P<identifier>(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?)(?:\.pdf)?$",
    re.I,
)
MAX_PDF_BYTES = 100 * 1024 * 1024


def download_arxiv_pdf(url: str, target: Path) -> str:
    pdf_url, identifier = arxiv_pdf_url(url)
    request = urllib.request.Request(
        pdf_url,
        headers={
            "User-Agent": "Papereading-Master-Beta/0.1",
            "Accept": "application/pdf",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            content_length = int(response.headers.get("Content-Length", "0") or "0")
            if content_length > MAX_PDF_BYTES:
                raise ExternalSearchError("The arXiv PDF is larger than 100 MB.")
            target.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with target.open("wb") as output:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_PDF_BYTES:
                        raise ExternalSearchError("The arXiv PDF is larger than 100 MB.")
                    output.write(block)
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        target.unlink(missing_ok=True)
        raise ExternalSearchError(f"Failed to download arXiv paper {identifier}.") from exc
    try:
        with target.open("rb") as source:
            header = source.read(5)
    except OSError as exc:
        raise ExternalSearchError(f"Failed to read downloaded arXiv paper {identifier}.") from exc
    if header != b"%PDF-":
        target.unlink(missing_ok=True)
        raise ExternalSearchError("The arXiv download did not return a valid PDF.")
    return pdf_url


def import_arxiv_paper(
    url: str,
    *,
    title: str,
    field: str = "arXiv",
    tags: tuple[str, ...] = (),
    repository: StudyRepository | None = None,
):
    repository = repository or StudyRepository()
    pdf_url, _identifier = arxiv_pdf_url(url)
    existing = next(
        (
            document
            for document in repository.list_documents()
            if document.source in {url, pdf_url}
        ),
        None,
    )
    if existing is not None:
        return existing, False
    with tempfile.TemporaryDirectory(prefix="paper-agent-arxiv-") as temp_dir:
        source_path = Path(temp_dir) / "paper.pdf"
        resolved_url = download_arxiv_pdf(url, source_path)
        duplicate = repository.find_duplicate_document(file_sha256(source_path))
        if duplicate is not None:
            return duplicate, False
        result = ingest_material(
            build_ingest_request(
                source_path=source_path,
                document_type=DocumentType.PAPER,
                field=field.strip() or "arXiv",
                title=title.strip() or "arXiv paper",
                source=resolved_url,
                tags=tags,
            ),
            repository=repository,
        )
        return result.document, True


def arxiv_pdf_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url.strip())
    host = (parsed.hostname or "").casefold()
    if host not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        raise ToolInputError("Only arXiv candidate papers can be downloaded automatically.")
    match = ARXIV_ID_RE.match(parsed.path.strip("/"))
    if not match:
        raise ToolInputError("Invalid arXiv paper URL.")
    identifier = match.group("identifier")
    return f"https://arxiv.org/pdf/{identifier}.pdf", identifier
