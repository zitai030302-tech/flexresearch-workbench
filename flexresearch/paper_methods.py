"""Extractive method cards: source sentences, not invented experimental advice.

This deterministic baseline identifies explicit method sections and categorizes
their sentences. It does not paraphrase, resolve contradictory protocols, or
claim that a missing match proves a paper omitted a parameter.
"""

import re
from typing import Literal

from pydantic import Field, model_validator

from .guardrails import prompt_injection_reasons
from .schemas import StrictModel


class PaperDocumentInput(StrictModel):
    document_id: int = Field(gt=0)


class PaperRetrievalInput(StrictModel):
    document_id: int | None = Field(default=None, gt=0, strict=True)
    paper_id: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def unique_source(self):
        if (self.document_id is None) == (self.paper_id is None):
            raise ValueError("Specify exactly one document_id or paper_id")
        return self


class PaperChunk(StrictModel):
    chunk_index: int
    page: int | None = None
    citation: str
    text: str
    char_start: int


class RetrievedPaper(StrictModel):
    document_id: int | None
    paper_id: int | None = None
    title: str
    source_file: str | None
    source_sha256: str | None
    evidence_level: Literal["document_text", "bibliographic_metadata_only"] = "document_text"
    metadata: dict = Field(default_factory=dict)
    chunks: list[PaperChunk]
    total_chunks: int
    truncated: bool = False

    @model_validator(mode="after")
    def metadata_is_not_text_evidence(self):
        if self.evidence_level == "bibliographic_metadata_only":
            if self.paper_id is None or self.document_id is not None or self.chunks or self.total_chunks or self.source_file or self.source_sha256 or self.truncated:
                raise ValueError("Bibliographic metadata cannot carry full-text evidence")
        elif self.document_id is None or not self.source_file or not self.source_sha256:
            raise ValueError("Document evidence requires an identified, hash-checked file")
        return self


class MethodEvidence(StrictModel):
    category: Literal["device", "electrodes", "acquisition", "processing", "validation"]
    quote: str
    citation: str
    page: int | None
    chunk_index: int
    # Exact offsets in the indexed source content, not PDF byte offsets.
    char_start: int
    char_end: int
    source_sha256: str


class MethodSummary(StrictModel):
    document_id: int
    title: str
    source_file: str
    source_sha256: str
    evidence: list[MethodEvidence]
    missing_categories: list[str]
    method_section_found: bool
    blocked_chunks: int
    status: Literal["complete", "partial", "no_evidence"]
    mode: Literal["extractive_rules"] = "extractive_rules"
    limitations: list[str]
    private_data_sent_externally: bool = False


CATEGORY_LABELS = {"device": "设备", "electrodes": "电极与材料", "acquisition": "采集条件", "processing": "数据处理", "validation": "验证方法"}
CATEGORY_PATTERNS = {
    "device": r"\b(?:AD5940|ADG732|AFE|MCU|instrument|analyzer|microcontroller|multiplexer)\b|设备|仪器|芯片|多路复用",
    "electrodes": r"\b(?:electrodes?|hydrogel|substrate|fabricat\w*)\b|电极|水凝胶|基底|制备",
    "acquisition": r"\b(?:sampl\w*|acqui\w*|frequenc\w*|current|voltage|Hz|kHz|MHz)\b|采样|采集|频率|电流|电压",
    "processing": r"\b(?:filter\w*|FFT|preprocess\w*|detrend\w*|Butterworth|algorithm|normaliz\w*)\b|滤波|预处理|去趋势|算法|归一化",
    "validation": r"\b(?:validat\w*|calibrat\w*|reference|repeats?|replicat\w*|comparison|control)\b|校准|验证|重复|参照|对照",
}
METHOD_HEADING = re.compile(r"^(?:\d+[.\d]*\s*)?(?:materials?\s+and\s+methods?|methods?|experimental(?:\s+(?:section|methods?|setup))?|实验方法|材料与方法|方法|实验步骤)\s*[:：]?$", re.I)
OTHER_HEADING = re.compile(r"^(?:\d+[.\d]*\s*)?(?:abstract|introduction|results?(?:\s+and\s+discussion)?|discussion|conclusions?|references|摘要|引言|结果(?:与讨论)?|讨论|结论|参考文献)\s*[:：]?$", re.I)


def extract_method(paper: RetrievedPaper) -> MethodSummary:
    if paper.evidence_level != "document_text":
        raise ValueError("没有摘要或全文证据，不能提取实验参数。")
    explicit_section = str(paper.metadata.get("section") or "").strip()
    in_method = bool(METHOD_HEADING.fullmatch(explicit_section))
    found = in_method
    evidence = []
    seen = set()
    blocked = 0
    for chunk in paper.chunks:
        if prompt_injection_reasons(chunk.text):
            blocked += 1
            continue
        for match in re.finditer(r"[^\n]+", chunk.text):
            line = match.group().strip()
            heading = line.lstrip("# ").strip()
            if METHOD_HEADING.fullmatch(heading):
                in_method = found = True
                continue
            if OTHER_HEADING.fullmatch(heading):
                in_method = False
                continue
            if not in_method:
                continue
            # Keep exact source spans; preserve negation, decimals and units.
            for sentence in re.finditer(r".+?(?:[。！？](?=\s|$)|(?<=[.!?])\s+(?=[A-Z])|$)", match.group()):
                original = sentence.group()
                quote = original.strip()
                if not quote or len(quote) > 700:
                    continue
                start = chunk.char_start + match.start() + sentence.start() + len(original) - len(original.lstrip())
                for category, pattern in CATEGORY_PATTERNS.items():
                    key = (category, quote)
                    if key in seen or not re.search(pattern, quote, re.I):
                        continue
                    seen.add(key)
                    evidence.append(MethodEvidence(category=category, quote=quote, citation=chunk.citation, page=chunk.page, chunk_index=chunk.chunk_index, char_start=start, char_end=start+len(quote), source_sha256=paper.source_sha256))
    missing = [category for category in CATEGORY_LABELS if not any(item.category == category for item in evidence)]
    limitations = ["这是明确方法章节中的原文摘录与规则分类，不是全文语义总结；需回到原文核对上下文。", "未匹配到某类内容不等于论文没有报告；未补全任何参数，也不把文献条件当作本实验操作建议。"]
    if not found:
        limitations.append("未识别到明确的方法章节标题；请补充 Methods 原文或为文档标注 section=Methods。")
    if paper.truncated:
        limitations.append("文档分块超过读取上限；本次只检查部分内容。")
    if blocked:
        limitations.append(f"{blocked} 个分块含指令注入模式，未作为方法证据。")
    status = "no_evidence" if not evidence else "partial" if missing or paper.truncated or blocked else "complete"
    return MethodSummary(document_id=paper.document_id, title=paper.title, source_file=paper.source_file, source_sha256=paper.source_sha256, evidence=evidence, missing_categories=missing, method_section_found=found, blocked_chunks=blocked, status=status, limitations=limitations)

