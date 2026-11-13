"""T023: 集成测试——一段混合输出的端到端校验（quickstart V3）。

校验后：交付文本中每一处保留下来的引用，原文必须与知识库逐字一致。
"""

from tu_assistant.citation.parse import parse_citations
from tu_assistant.citation.verify import NOT_FOUND_PLACEHOLDER, verify_output
from tu_assistant.kb.models import DocumentMeta
from tu_assistant.kb.parse import parse_clauses
from tu_assistant.kb.readers import read_document
from tu_assistant.kb.store import (
    create_kb,
    doc_id_for,
    insert_clause,
    insert_document,
)

LAW_TEXT = """用人单位不得阻挠职工依法参加和组织工会。"""


def _kb():
    from pathlib import Path

    lines = read_document(Path(__file__).parent.parent / "fixtures" / "law_sample.txt")
    meta = DocumentMeta(title="示例工会法", version_label="2020")
    meta.doc_id = doc_id_for(meta.title, meta.version_label)
    conn = create_kb(":memory:")
    insert_document(conn, meta)
    for c in parse_clauses(lines, meta.doc_id)[0]:
        insert_clause(conn, c)
    conn.commit()
    return conn


def test_mixed_output_end_to_end():
    conn = _kb()
    output = """## 违法行为认定

### 1. 用人单位：阻挠组建工会

**适用条款**
〔《示例工会法》（2020）第四条〕
> 用人单位可以阻挠职工组建工会。

**法律责任**
〔《示例工会法》（2020）第八条〕

**补充**
〔《示例工会法》（2020）第九十九条〕
> 不存在的条款。
另外，第六条规定了上级工会的指导职责。
"""
    r = verify_output(output, conn)
    stats = r.stats
    assert stats["corrected"] == 1     # 第四条原文被纠正
    assert stats["ok"] == 1            # 第八条省略原文自动补入
    assert stats["not_found"] == 1     # 第九十九条删除
    assert stats["incomplete"] == 1    # "第六条"裸引用

    # 交付文本逐条复核：每个保留下来的引用，其原文与知识库一致
    assert "可以阻挠" not in r.text
    assert LAW_TEXT in r.text
    assert "责令其改正" in r.text          # 第八条自动补入的原文
    assert NOT_FOUND_PLACEHOLDER in r.text
    assert "不存在的条款" not in r.text

    # 复核：校验后文本中重新解析出的引用，quoted_text 全部与库一致
    verified = parse_citations(r.text)
    kept = [c for c in verified if c.title]
    assert kept  # 至少有第四条、第八条
    r2 = verify_output(r.text, conn)
    assert r2.stats["corrected"] == 0 and r2.stats["not_found"] == 0
