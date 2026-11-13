"""文档读取：把不同格式的文件统一转成纯文本行列表。

支持：.txt（项目方当前文档均为纯文本）、.docx、文本型 .pdf、.html。
扫描件 / 图片型 PDF 不在范围内（spec 假设）。
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".docx", ".pdf", ".html", ".htm"}


def read_document(path: str | Path) -> list[str]:
    """读取文档，返回去除空白的行列表（保留空行以外的所有行）。"""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".txt":
        text = p.read_text(encoding="utf-8")
    elif suffix == ".docx":
        text = _read_docx(p)
    elif suffix == ".pdf":
        text = _read_pdf(p)
    elif suffix in {".html", ".htm"}:
        text = _read_html(p)
    else:
        raise ValueError(f"不支持的文件格式：{p.name}（{suffix}）")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _read_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    return "\n".join(para.text for para in doc.paragraphs)


def _read_pdf(path: Path) -> str:
    import pdfplumber

    parts = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _read_html(path: Path) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")
