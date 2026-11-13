"""知识库数据类型（data-model.md §1）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentMeta:
    """一份法律文件的元数据。"""

    title: str
    version_label: str = ""
    issuer: str | None = None
    level: str | None = None
    promulgated_on: str | None = None
    status: str = "current"  # current / amended / repealed
    corpus: str = "project"
    source_file: str = ""
    doc_id: str = ""


@dataclass
class Clause:
    """条款：可被引用的最小单元（条 / 款 / 项）。"""

    doc_id: str
    article_no: int
    paragraph_no: int | None
    item_no: int | None
    number_text: str
    heading_path: list[str] = field(default_factory=list)
    text: str = ""
    clause_type: str = "other"  # obligation/prohibition/right/liability/other
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def clause_id(self) -> str:
        parts = [self.doc_id, f"a{self.article_no}"]
        if self.paragraph_no is not None:
            parts.append(f"p{self.paragraph_no}")
        if self.item_no is not None:
            parts.append(f"i{self.item_no}")
        return ":".join(parts)


@dataclass
class ClauseRelation:
    from_clause_id: str
    to_clause_id: str
    relation_type: str  # liability_for / references / exception_of
    origin: str = "rule"  # rule / llm / manual
    confirmed: bool = False
