"""Upload-scoped document indexing contracts and side-effect-free preparation.

Raw bytes stay in a request-owned closure, never in function arguments or tool
logs. The bounded worker only parses/chunks/embeds. The application commits the
validated preparation atomically; timed-out workers have no write capability.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field, model_validator
from werkzeug.utils import secure_filename

from .schemas import StrictModel
from .retrieval import embed_text, serialize_embedding


class DocumentMetadata(StrictModel):
    paper_title: str = Field(default="", max_length=240)
    year: str | None = Field(default=None, max_length=12)
    journal: str | None = Field(default=None, max_length=160)
    section: str | None = Field(default=None, max_length=120)


class IndexDocumentInput(StrictModel):
    upload_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    title: str = Field(default="", max_length=160)
    experiment_id: int | None = Field(default=None, gt=0)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


@dataclass(frozen=True)
class DocumentUpload:
    upload_id: str
    filename: str
    raw: bytes
    mimetype: str = "application/octet-stream"


class PreparedChunk(StrictModel):
    index: int
    page: int | None
    start: int
    end: int
    text: str
    vector: bytes = Field(exclude=True)


class PreparedDocument(StrictModel):
    arguments: IndexDocumentInput
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filename: str
    extension: str
    mimetype: str
    raw: bytes = Field(exclude=True)
    content: str = Field(default="", exclude=True)
    chunks: list[PreparedChunk] = Field(default_factory=list, exclude=True)
    error_code: str | None = None
    error: str | None = None


class IndexedDocumentSummary(StrictModel):
    id: int = Field(gt=0)
    title: str
    filename: str
    extension: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: str
    metadata: dict[str, Any]
    characters: int = Field(gt=0)
    pages: int = Field(gt=0)
    excerpt: str
    chunks: int = Field(gt=0)


class DocumentCitation(StrictModel):
    chunk_index: int = Field(ge=0)
    page: int | None = Field(default=None, gt=0)
    locator: str
    citation: str
    url: str


class IndexDocumentOutput(StrictModel):
    response_state: Literal["completed", "needs_clarification"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    document: IndexedDocumentSummary | None = None
    duplicate: bool = False
    citations: list[DocumentCitation] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None
    method_claims: list[str] = Field(default_factory=list, max_length=0)
    private_data_sent_externally: Literal[False] = False

    @model_validator(mode="after")
    def consistent_result(self):
        if self.response_state == "completed":
            if not self.document or self.error_code or self.error or not self.citations or self.document.sha256 != self.source_sha256:
                raise ValueError("completed indexing requires a source-bound document and citations")
            if len(self.citations) != self.document.chunks:
                raise ValueError("indexed chunk and citation counts differ")
        elif self.document or self.citations or self.duplicate or not self.error_code or not self.error:
            raise ValueError("clarification must not claim an indexed document")
        return self


def prepare_document(payload: IndexDocumentInput, upload: DocumentUpload | None, extract: Callable, split: Callable) -> PreparedDocument:
    if upload is None or payload.upload_id != upload.upload_id:
        raise ValueError("上传授权不存在或不属于当前请求；未读取任何文件。")
    name = Path(upload.filename).name
    extension = Path(name).suffix.lower()
    prepared = PreparedDocument(arguments=payload, source_sha256=hashlib.sha256(upload.raw).hexdigest(), filename=secure_filename(name) or f"document{extension}", extension=extension, mimetype=upload.mimetype, raw=upload.raw)
    if not upload.raw or extension not in {".txt", ".md", ".csv", ".pdf"}:
        return prepared.model_copy(update={"error_code": "DOCUMENT_INPUT_INVALID", "error": "请提供非空 TXT、Markdown、CSV 或 PDF 文档。"})
    try:
        # Do not strip form feeds: empty physical pages still occupy page IDs.
        content = extract(name, upload.raw).replace("\r\n", "\n").replace("\r", "\n").strip(" \t\r\n")
    except ValueError as exc:
        return prepared.model_copy(update={"error_code": "DOCUMENT_PARSE_FAILED", "error": str(exc)})
    if not content.strip():
        return prepared.model_copy(update={"error_code": "OCR_REQUIRED" if extension == ".pdf" else "DOCUMENT_TEXT_EMPTY", "error": "未能提取可检索文本；扫描版 PDF 需要先完成 OCR，未生成方法或参数。"})
    if len(content) > 2_000_000:
        return prepared.model_copy(update={"error_code": "DOCUMENT_TEXT_TOO_LARGE", "error": "提取文本超过当前索引上限，请拆分文档；未归档不完整索引。"})
    chunks = []
    for index, (start, end, text) in enumerate(split(content)):
        page = content.count("\f", 0, start) + 1 if "\f" in content or extension == ".pdf" else None
        chunks.append(PreparedChunk(index=index, page=page, start=start, end=end, text=text, vector=serialize_embedding(embed_text(text))))
    return prepared.model_copy(update={"content": content, "chunks": chunks})

