from finals_agent.core.exceptions import ToolInputError
from finals_agent.data.paper_download import arxiv_pdf_url


def test_arxiv_abs_url_is_converted_to_pdf_url():
    url, identifier = arxiv_pdf_url("https://arxiv.org/abs/2605.01106v1")

    assert identifier == "2605.01106v1"
    assert url == "https://arxiv.org/pdf/2605.01106v1.pdf"


def test_non_arxiv_url_is_rejected():
    try:
        arxiv_pdf_url("https://example.com/paper.pdf")
    except ToolInputError:
        return
    raise AssertionError("non-arXiv URL should be rejected")
