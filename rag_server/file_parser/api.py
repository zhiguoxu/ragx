from fastapi import APIRouter

from file_parser.docling_wrapper.docling import docling_pdf_to_markdown
from file_parser.model import ParseFileRequest

router = APIRouter(prefix="/file_parser", tags=["file parser"])


@router.post("/pdf_to_markdown/docling")
def pdf_to_markdown_by_docling(request: ParseFileRequest) -> list[list[str]]:
    return [docling_pdf_to_markdown(url, file_node_id, request.notify_url)
            for url, file_node_id in zip(request.file_urls, request.file_node_ids)]
