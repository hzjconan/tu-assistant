"""tu 命令入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="工会法律条款智能助手（POC）命令行工具")
kb_app = typer.Typer(help="知识库：导入、查看、关联")
app.add_typer(kb_app, name="kb")


@app.callback()
def _main() -> None:
    """工会法律条款智能助手（POC）命令行工具。"""


@app.command()
def version() -> None:
    """显示版本。"""
    typer.echo("tu-assistant 0.1.0")


def _resolve_cli_kb(
    kb_version: str | None = None,
    *,
    config: dict | None = None,
    artifacts: str | None = None,
) -> Path:
    from .kb.store import KBError, resolve_kb_path

    try:
        return resolve_kb_path(kb_version, config=config, artifacts_dir=artifacts)
    except KBError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(2) from e


@kb_app.command("import")
def kb_import(
    directory: str = typer.Argument(..., help="文档目录（如 inputs/project/）"),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """整批导入文档，拆分条款并入库校验，生成新知识库版本。"""
    from .kb.ingest import import_directory

    result = import_directory(directory, artifacts)
    typer.echo(
        f"kb_version={result['kb_version']}  文件 {result['files']} 篇 / "
        f"条款 {result['clauses']} 条 / 问题 {result['issues']} 个"
    )
    typer.echo(f"校验报告：{result['report']}")


@kb_app.command("derive")
def kb_derive(
    source_kb: str = typer.Argument(..., help="源知识库版本（如 kb-20261113-093057）或 sqlite 路径"),
    kb_version: str | None = typer.Option(None, "--kb-version", help="派生后的新版本号，默认按时间戳生成"),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """从已有 SQLite 知识库派生新版本，补齐多款条文第一款显式款号（不改旧库）。"""
    from .kb.derive import derive_kb

    src = Path(source_kb)
    if not src.exists():
        src = Path(artifacts, "kb", f"{source_kb}.sqlite")
    try:
        res = derive_kb(src, artifacts, kb_version=kb_version)
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError) as e:
        typer.secho(f"派生失败：{e}", fg="red", err=True)
        raise typer.Exit(2) from e
    typer.echo(
        f"kb_version={res['kb_version']}  derived_from={res['derived_from']}  "
        f"文件 {res['files']} 篇 / 条款 {res['clauses']} 行 / "
        f"更新多款条文 {res['multi_para_articles_updated']} 条（{res['number_text_rows_updated']} 行）"
    )
    typer.echo(f"新库：{res['sqlite']}  sha256={res['sqlite_sha256'][:16]}")
    typer.echo(f"清单：{res['manifest']}")


@kb_app.command("list")
def kb_list(
    kb_version: str | None = typer.Option(None, help="知识库版本，默认最新"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """列出知识库中的文件（供人工核对）。"""
    from .kb.store import list_documents, open_kb

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)
    for d in list_documents(conn):
        typer.echo(
            f"{d['title']}（{d['version_label'] or '无版本'}）"
            f"[{d['status']}] 条款 {d['clauses']} 条"
        )
    conn.close()


@kb_app.command("show")
def kb_show(
    title: str = typer.Argument(..., help="文件全称（不含书名号）"),
    article_no: int = typer.Argument(..., help="条号（整数）"),
    paragraph: int | None = typer.Option(None, "--paragraph", "-p"),
    item: int | None = typer.Option(None, "--item", "-i"),
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """查看某条款原文，便于人工核对。"""
    from .kb.store import article_clauses, get_clause, open_kb

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)
    if paragraph is None and item is None:
        rows = article_clauses(conn, title, article_no)
    else:
        c = get_clause(conn, title, article_no, paragraph, item)
        rows = [c] if c else []
    conn.close()
    if not rows:
        typer.secho("未找到该条款", fg="red")
        raise typer.Exit(1)
    for c in rows:
        typer.echo(f"{c.number_text}\n{c.text}\n")


@kb_app.command("lookup")
def kb_lookup(
    clause_id: str = typer.Argument(..., help="条款 ID，如 3296db5b22b8ea1d:a24:p1"),
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """按 clause_id 查条款（核对关联候选时用）。"""
    from .kb.store import get_clause_by_id, get_document, open_kb

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)
    c = get_clause_by_id(conn, clause_id)
    doc = get_document(conn, c.doc_id) if c else None
    conn.close()
    if not c or not doc:
        typer.secho("未找到该条款", fg="red")
        raise typer.Exit(1)
    typer.echo(f"{doc.title}（{doc.version_label or '无版本'}）{c.number_text}\n{c.text}\n")


@kb_app.command("diff")
def kb_diff(
    v1: str = typer.Argument(..., help="旧知识库版本（如 kb-20261113-093057）或 sqlite 路径"),
    v2: str = typer.Argument(..., help="新知识库版本（如 kb-20261119-045641）或 sqlite 路径"),
    summary_only: bool = typer.Option(
        False, "--summary-only", help="仅输出汇总与文件级变化，不展开逐条条款编号清单"
    ),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """对比两个知识库版本的新增、删除、原文变化条款（只输出编号与变化类型，不输出条文正文）。"""
    from .kb.diff import diff_kbs, render_diff
    from .kb.store import KBError

    try:
        res = diff_kbs(v1, v2, artifacts_dir=artifacts)
    except KBError as e:
        typer.secho(f"对比失败：{e}", fg="red", err=True)
        raise typer.Exit(2) from e
    typer.echo(render_diff(res, summary_only=summary_only), nl=False)


relations_app = typer.Typer(help="条款关联：抽取与人工确认")
kb_app.add_typer(relations_app, name="relations")


@relations_app.command("extract")
def relations_extract(
    kb_version: str | None = typer.Option(None, "--kb-version", help="知识库版本，默认最新"),
    out: str | None = typer.Option(
        None,
        "--out",
        help="输出 jsonl 路径（默认 artifacts/kb/<ver>-relations_pending.jsonl）",
    ),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """用规则抽取条款关联候选，输出 relations_pending.jsonl 待人工确认。"""
    import json as _json
    from itertools import groupby

    from .kb.relations import extract_relations
    from .kb.store import all_clauses, open_kb

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)
    clauses = all_clauses(conn)
    conn.close()

    pending = []
    for _doc_id, group in groupby(clauses, key=lambda c: c.doc_id):
        pending.extend(extract_relations(list(group)))

    out_path = Path(out) if out else Path(artifacts, "kb", f"{kb_path.stem}-relations_pending.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in pending:
            f.write(
                _json.dumps(
                    {
                        "from_clause_id": r.from_clause_id,
                        "to_clause_id": r.to_clause_id,
                        "relation_type": r.relation_type,
                        "origin": r.origin,
                        "decision": "pending",
                        "confirmed": False,
                        "evidence": r.evidence,
                        "scope": r.scope,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    typer.echo(f"候选关联 {len(pending)} 条 → {out_path}")
    typer.echo(
        f"请用 tu kb relations review {out_path} --kb-version {kb_path.stem} 核对，"
        f"完成后运行 tu kb relations confirm {out_path} --kb-version {kb_path.stem}"
    )


@relations_app.command("confirm")
def relations_confirm(
    file: str = typer.Argument(..., help="人工审阅后的 jsonl 文件"),
    kb_version: str = typer.Option(..., "--kb-version", help="目标新知识库版本（拒绝写入历史/只读版本）"),
    batch: str | None = typer.Option(None, "--batch", help="批次标识（记录进 manifest）"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """事务化差异导入人工审阅后的条款关联（支持 confirm/revoke/reject/pending）。"""
    from .kb.relations import RelationImportError, apply_relations_diff

    try:
        res = apply_relations_diff(file, kb_version, artifacts, batch=batch)
    except RelationImportError as e:
        typer.secho(f"导入失败：{e}", fg="red", err=True)
        raise typer.Exit(2) from e
    typer.echo(
        f"已导入 {res['kb_version']}：确认 {res['confirmed']} / "
        f"撤销 {res['revoked']}（实际删除 {res['revoked_deleted']}） / "
        f"拒绝 {res['rejected']} / 待查 {res['pending']}；"
        f"库内已确认合计 {res['total_confirmed_after']} 条"
    )
    missed = res["revoked"] - res["revoked_deleted"]
    if missed > 0:
        typer.secho(
            f"警告：有 {missed} 条 revoke 边在目标知识库中本就不存在（未删除任何行），"
            "请确认是否为重复导入或失效旧边。",
            fg="yellow",
            err=True,
        )


@relations_app.command("review")
def relations_review(
    file: str = typer.Argument(..., help="relations_pending.jsonl 路径"),
    kb_version: str | None = typer.Option(None, "--kb-version", help="知识库版本，默认最新"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """交互式核对关联候选：查看完整原文（含子项）、所属条总款数与触发片段，标记四态决策。"""
    import json as _json

    from .kb.relations import article_paragraph_count, canonical_clause_text
    from .kb.store import get_clause_by_id, get_document, open_kb

    path = Path(file)
    rows = [
        _json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        if "decision" not in row:
            row["decision"] = "confirm" if row.get("confirmed") else "pending"

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)

    def save() -> None:
        path.write_text(
            "".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )

    def show(idx: int) -> None:
        r = rows[idx]
        in_db = bool(
            conn.execute(
                "SELECT 1 FROM clause_relations "
                "WHERE from_clause_id=? AND to_clause_id=? AND relation_type=? AND confirmed=1",
                (r["from_clause_id"], r["to_clause_id"], r["relation_type"]),
            ).fetchone()
        )
        db_tag = "库内已有旧边" if in_db else "库内未入库"
        extra_meta = [db_tag]
        if r.get("scope"):
            extra_meta.append(f"scope={r['scope']}")
        if r.get("evidence"):
            extra_meta.append(f"触发={r['evidence']}")
        meta_s = "，" + "，".join(extra_meta)
        typer.echo(
            f"\n[{idx + 1}/{len(rows)}] {r['relation_type']}"
            f"（origin={r.get('origin')}，当前 decision={r['decision']}{meta_s}）"
        )
        if r.get("suggested_decision") or r.get("note"):
            typer.echo(
                f"  提示: 建议={r.get('suggested_decision') or '-'} | {r.get('note') or ''}"
            )
        if r.get("llm_verdict") or r.get("llm_reason"):
            typer.echo(
                f"  预审: {r.get('llm_verdict') or '-'} | {r.get('llm_reason') or ''}"
            )
        for label, key in (("from", "from_clause_id"), ("to", "to_clause_id")):
            c = get_clause_by_id(conn, r[key])
            doc = get_document(conn, c.doc_id) if c else None
            if c and doc:
                para_note = ""
                if label == "from":
                    total_p = article_paragraph_count(conn, c)
                    para_note = f" [该条共 {total_p} 款，当前第 {c.paragraph_no or 1} 款]"
                typer.echo(
                    f"  {label}: {doc.title}（{doc.version_label or '无版本'}）"
                    f"{c.number_text}{para_note}  ({c.clause_id})"
                )
                typer.echo(f"        {canonical_clause_text(conn, c)}")
            else:
                typer.echo(f"  {label}: {r[key]}（未在库中找到）")

    typer.echo(
        f"共 {len(rows)} 条。用法：行号=查看并标记；行号 y/n/p/r=直接标记；q=退出。"
        "标记时回车/y=confirm，n=reject，p/s=pending（待查），r=revoke（撤销旧边）"
    )
    while True:
        try:
            line = input("\n行号> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("q", "quit", "exit"):
            break
        if not line:
            continue
        parts = line.split()
        try:
            idx = int(parts[0]) - 1
        except ValueError:
            typer.echo("请输入行号（1 起始），或 q 退出")
            continue
        if not 0 <= idx < len(rows):
            typer.echo(f"超出范围（1–{len(rows)}）")
            continue
        show(idx)
        verdict = parts[1] if len(parts) > 1 else None
        if verdict is None:
            try:
                verdict = input("decision? [Y(confirm)/n(reject)/p(pending)/r(revoke)] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
        if verdict in ("", "y", "t", "true", "1", "c", "confirm"):
            rows[idx]["decision"] = "confirm"
            rows[idx]["confirmed"] = True
        elif verdict in ("n", "f", "false", "0", "reject"):
            rows[idx]["decision"] = "reject"
            rows[idx]["confirmed"] = False
        elif verdict in ("r", "revoke"):
            rows[idx]["decision"] = "revoke"
            rows[idx]["confirmed"] = False
        elif verdict in ("p", "s", "skip", "pending"):
            rows[idx]["decision"] = "pending"
            rows[idx]["confirmed"] = False
        else:
            typer.echo("未识别的输入，未修改")
            continue
        save()
        done = sum(1 for r in rows if r.get("decision") == "confirm")
        rev = sum(1 for r in rows if r.get("decision") == "revoke")
        typer.echo(
            f"→ decision={rows[idx]['decision']}（累计 confirm {done} / revoke {rev} / 共 {len(rows)}）"
        )

    conn.close()
    typer.echo(
        f"\n已保存 {path}。全部核完后运行："
        f"uv run tu kb relations confirm {path} --kb-version {kb_path.stem}"
    )


serve_app = typer.Typer(help="模型服务")
app.add_typer(serve_app, name="serve")


@serve_app.command("model")
def serve_model(
    exp: str = typer.Option(..., "--exp", help="实验 ID（artifacts/train/<exp>）"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8080),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """启动本地模型端点（mlx_lm.server，只监听本机）。"""
    import json as _json
    import subprocess
    import sys

    if host not in {"127.0.0.1", "localhost"}:
        typer.secho("模型端点只监听本机（127.0.0.1 / localhost）", fg="red")
        raise typer.Exit(1)

    exp_dir = Path(artifacts, "train", exp)
    manifest = _json.loads((exp_dir / "manifest.json").read_text(encoding="utf-8"))
    base = manifest["config"]["base_model"]
    adapter = exp_dir / "adapters"
    if not adapter.exists():
        typer.secho(f"适配器不存在：{adapter}", fg="red")
        raise typer.Exit(1)

    # mlx_lm.server 仅当请求的 model 字段为 "default_model" 时才挂 --adapter-path
    # 指定的 adapter（E002）；写具体基座模型名会被路由到不带 adapter 的基座。
    serve_dir = Path(artifacts, "serve")
    serve_dir.mkdir(parents=True, exist_ok=True)
    (serve_dir / "current.json").write_text(
        _json.dumps(
            {"model": "default_model", "base_model": base, "exp": exp,
             "endpoint": f"http://{host}:{port}/v1"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cmd = [
        sys.executable, "-m", "mlx_lm.server",
        "--model", base,
        "--adapter-path", str(adapter),
        "--host", host,
        "--port", str(port),
    ]
    typer.echo("启动：" + " ".join(cmd))
    subprocess.run(cmd)


def _model_name(cfg, artifacts: str) -> str:
    """兼容封装：委托给 config.resolve_model_name。"""
    from .config import resolve_model_name

    return resolve_model_name(cfg, artifacts)


synth_app = typer.Typer(help="数据合成（唯一使用外部大模型的命令组）")
eval_app = typer.Typer(help="评测")
eval_cases_app = typer.Typer(help="评测用例核对")
eval_app.add_typer(eval_cases_app, name="cases")
app.add_typer(synth_app, name="synth")
app.add_typer(eval_app, name="eval")


@synth_app.command("evalcases")
def synth_evalcases(
    kb_version: str | None = typer.Option(None),
    n: int = typer.Option(40, help="候选用例数"),
    artifacts: str = typer.Option("artifacts"),
    synth_config: str = typer.Option("configs/synth.yaml"),
) -> None:
    """生成评测候选用例（调用外部大模型，需 TU_EXTERNAL_LLM_API_KEY）。"""
    from .config import load_synth_config
    from .kb.store import open_kb
    from .synth.evalcases import generate_candidates
    from .synth.llm import from_config

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)
    llm = from_config(load_synth_config(synth_config))
    result = generate_candidates(conn, llm, n=n)
    conn.close()
    typer.echo(f"候选用例 {result['written']} 条 → {result['path']}")


@synth_app.command("sft")
def synth_sft(
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
    synth_config: str = typer.Option("configs/synth.yaml"),
    eval_cases: str = typer.Option("eval/cases/v1", help="评测集目录（去重用）"),
    skip_llm: bool = typer.Option(False, help="只用确定性样本（调试用）"),
    reuse_dataset: str | None = typer.Option(
        None, help="复用已有 train/valid 中的样本，只补新生成部分"
    ),
    reuse_only: bool = typer.Option(
        False, "--reuse-only", help="只重建数据集，不再生成任何新样本"
    ),
    refresh_relations: bool = typer.Option(
        False, "--refresh-relations", help="复用旧库时清理旧关系样本并注入当前 KB 全部确认关系"
    ),
    articles_file: list[str] | None = typer.Option(  # noqa: B008
        None, "--articles-file", help="经人工复审固化的文章样本 JSONL（可重复传多次）"
    ),
    preserve_split: bool = typer.Option(
        True, "--preserve-split/--no-preserve-split", help="复用旧数据集时保持原 train/valid 归属"
    ),
) -> None:
    """生成 SFT 训练样本并构建数据集。"""
    from collections import Counter

    from .config import load_synth_config
    from .eval.cases import eval_questions, load_cases
    from .kb.store import open_kb
    from .synth import articles, consult, dialogs, general, knowledge, refusal
    from .synth.check import CheckStats, check_sample
    from .synth.llm import from_config
    from .train.dataset import (
        balance_by_doc,
        dedup_against_eval,
        load_message_samples,
        relation_kind_of,
        write_dataset,
    )

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    if reuse_only and not reuse_dataset:
        typer.secho("--reuse-only 需要同时提供 --reuse-dataset", fg="red")
        raise typer.Exit(1)

    conn = open_kb(kb_path, read_only=True)
    cfg = load_synth_config(synth_config)
    llm = None if skip_llm else from_config(cfg)
    titles = knowledge.doc_titles(conn)

    if reuse_dataset:
        samples = load_message_samples(reuse_dataset, conn)
        typer.echo(f"复用已有样本 {len(samples)} 条 → {reuse_dataset}")
    else:
        samples = knowledge.generate(conn, llm, cfg)

    relation_refresh_stats: dict | None = None
    if refresh_relations:
        def _rel_sig(s: dict) -> tuple[str | None, tuple[str, ...]]:
            rk = relation_kind_of(s.get("messages", []))
            cids = tuple(sorted((s.get("meta") or {}).get("clause_ids") or []))
            return rk, cids

        old_train_rel_sigs = {
            _rel_sig(s)
            for s in samples
            if (s.get("meta") or {}).get("split") == "train"
            and relation_kind_of(s.get("messages", [])) is not None
        }
        before_rel = len(samples)
        samples = [s for s in samples if relation_kind_of(s.get("messages", [])) is None]
        removed_old = before_rel - len(samples)
        new_rels = knowledge.relation_samples(conn, titles)
        for rel_s in new_rels:
            if _rel_sig(rel_s) in old_train_rel_sigs:
                rel_s.setdefault("meta", {})["split"] = "train"
        samples.extend(new_rels)
        by_kind = Counter(s.get("meta", {}).get("kind", "unknown") for s in new_rels)
        relation_refresh_stats = {
            "removed_old": removed_old,
            "added_new": len(new_rels),
            "by_kind": dict(by_kind),
        }
        typer.echo(f"刷新条款关系样本：剔除旧关系 {removed_old} 条，注入新关系 {len(new_rels)} 条")

    article_sources: list[str] = []
    if articles_file:
        if reuse_dataset:
            old_art = sum(1 for s in samples if s.get("meta", {}).get("type") == "article")
            if old_art:
                samples = [s for s in samples if s.get("meta", {}).get("type") != "article"]
                typer.echo(f"传入 --articles-file，已剔除复用库旧文章样本 {old_art} 条")
        loaded_articles: list[dict] = []
        for af in articles_file:
            p = Path(af)
            if not p.exists():
                typer.secho(f"文章样本文件不存在：{p}", fg="red")
                conn.close()
                raise typer.Exit(1)
            article_sources.append(str(p))
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                meta = row.get("meta") or {}
                if meta.get("type") != "article":
                    typer.secho(f"{p} 中存在非 article 样本：{meta.get('type')}", fg="red")
                    conn.close()
                    raise typer.Exit(1)
                loaded_articles.append(row)

        draft_ids: set[str] = set()
        normalized_articles: list[dict] = []
        for row in loaded_articles:
            meta = row.get("meta") or {}
            if not meta.get("parent"):
                did = articles.draft_id(row)
                draft_ids.add(did)
                norm = articles.normalize_draft_markers(row, conn)
                norm.setdefault("meta", {})["sample_id"] = did
                normalized_articles.append(norm)
            else:
                normalized_articles.append(row)
        missing_parents = [
            (r.get("meta") or {}).get("parent")
            for r in normalized_articles
            if (r.get("meta") or {}).get("parent")
            and (r.get("meta") or {}).get("parent") not in draft_ids
        ]
        if missing_parents:
            typer.secho(
                f"检测到孤儿修改稿（parent 缺失对应初稿）：{missing_parents[:5]}", fg="red"
            )
            conn.close()
            raise typer.Exit(1)
        samples.extend(normalized_articles)
        typer.echo(f"合入已审文章样本 {len(normalized_articles)} 条（来自 {len(article_sources)} 个文件）")

    if not reuse_only:
        if llm is not None:
            behavior = cfg.get("behavior", {})
            samples += dialogs.generate(
                conn, llm, cfg,
                n_per_variant=behavior.get("intent_samples", 20),
            )
            samples += consult.generate(
                conn, llm, cfg,
                n_single=behavior.get("consult_single", 40),
                n_multi=behavior.get("consult_multi", 20),
            )
        samples += refusal.generate(llm, cfg)
        general_target = int(len(samples) * cfg.get("general_ratio", 0.05))
        samples += general.generate(llm, cfg, target=general_target)

    # 检查：引用可解析、条款存在、原文一致（assistant 输出部分）
    stats = CheckStats()
    consult_drop_docs: Counter[str] = Counter()
    kept = []
    for s in samples:
        last = s["messages"][-1]
        meta = s.get("meta", {})
        requires_citation = meta.get("type") not in {"refusal", "general"}
        if last["role"] == "assistant" and not check_sample(
            last["content"],
            conn,
            stats,
            require_citation=requires_citation,
            expected_clause_ids=set(meta.get("clause_ids", [])),
        ):
            if meta.get("type") == "consult":
                doc_id = meta.get("doc_id") or "unknown"
                doc_name = titles[doc_id][0] if doc_id in titles else doc_id
                consult_drop_docs[doc_name] += 1
            continue
        kept.append(s)
    conn.close()
    typer.echo(f"样本检查：{stats.kept} 保留 / {stats.dropped} 丢弃 {stats.reasons}")

    # 与评测集去重
    cases_dir = Path(eval_cases)
    questions = eval_questions(load_cases(cases_dir)) if cases_dir.exists() else []
    if not questions:
        typer.secho(f"警告：评测集路径 {cases_dir} 加载到 0 条问句，去重未生效", fg="yellow")
    kept, dropped = dedup_against_eval(kept, questions)
    if dropped:
        typer.echo(f"与评测集去重：剔除 {len(dropped)} 条（对照 {len(questions)} 条评测问句）")

    art_before_bal = sum(1 for s in kept if s.get("meta", {}).get("type") == "article")
    kept = balance_by_doc(kept, seed=cfg.get("seed", 42))
    art_after_bal = sum(1 for s in kept if s.get("meta", {}).get("type") == "article")

    # knowledge 抽稀在 write_dataset 内执行（manifest 记真实前后值），
    # 这里只估算抽稀后的总数用于 dataset_id。
    knowledge_max = cfg.get("knowledge_max")
    n_out = len(kept)
    if knowledge_max:
        n_know = sum(
            1 for s in kept if s.get("meta", {}).get("type") == "knowledge"
        )
        n_out -= max(0, n_know - knowledge_max)
    dataset_id = f"ds-{kb_path.stem}-{n_out}"
    generator = llm.meta() if llm else {"provider": "deterministic"}
    if reuse_dataset:
        generator["reuse_dataset"] = str(reuse_dataset)
        reuse_manifest = Path(reuse_dataset, "manifest.json")
        if reuse_manifest.exists():
            generator["reuse_manifest"] = json.loads(
                reuse_manifest.read_text(encoding="utf-8")
            )
    if reuse_only:
        generator["mode"] = "reuse_only"

    # 汇总 manifest 扩展信息（已知限制、关系刷新、淘汰 consult 分布、文章统计与去重留痕）
    kept_articles = [s for s in kept if s.get("meta", {}).get("type") == "article"]
    extra_manifest: dict = {
        "known_issues": list(cfg.get("known_issues") or []),
        "split_integrity": {
            "preserved_from_reuse": bool(reuse_dataset and preserve_split),
            "dedup_eval_cases_dir": str(cases_dir),
            "dedup_eval_questions": len(questions),
            "dedup_dropped": len(dropped),
        },
    }
    if relation_refresh_stats is not None:
        extra_manifest["relation_refresh"] = relation_refresh_stats
    if consult_drop_docs:
        extra_manifest["consult_check_drops"] = {
            "total": sum(consult_drop_docs.values()),
            "by_doc": dict(consult_drop_docs.most_common()),
        }
    if kept_articles:
        kind_cnt = Counter((s.get("meta") or {}).get("kind", "unknown") for s in kept_articles)
        doc_cnt = Counter(
            titles[s["meta"]["doc_id"]][0]
            if (s.get("meta") or {}).get("doc_id") in titles
            else (s.get("meta") or {}).get("doc_id", "unknown")
            for s in kept_articles
        )
        fam_ids = {
            (s.get("meta") or {}).get("parent") or articles.draft_id(s)
            for s in kept_articles
        }
        extra_manifest["article_stats"] = {
            "total": len(kept_articles),
            "drafts": sum(1 for s in kept_articles if not (s.get("meta") or {}).get("parent")),
            "revisions": sum(1 for s in kept_articles if (s.get("meta") or {}).get("parent")),
            "families": len(fam_ids),
            "dropped_by_balance": art_before_bal - art_after_bal,
            "by_kind": dict(kind_cnt),
            "by_doc": dict(doc_cnt),
            "sources": article_sources,
        }

    result = write_dataset(
        kept, dataset_id, Path(artifacts, "datasets"),
        kb_version=kb_path.stem,
        generator=generator,
        eval_set_version="v1" if questions else None,
        seed=cfg.get("seed", 42),
        train_oversample=cfg.get("train_oversample", {}),
        add_system_prompt=cfg.get("add_system_prompt", False),
        knowledge_max=knowledge_max,
        preserve_split=preserve_split,
        extra_manifest=extra_manifest,
    )
    # 落盘后核对：复算 unify_system_prompts 之后最终文章样本 token 分布，并核对 valid ∩ 旧 train = 0
    if kept_articles or (reuse_dataset and preserve_split):
        from statistics import median

        from .config import load_yaml

        out_dir = Path(result["dir"])
        manifest_path = out_dir / "manifest.json"
        mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
        if reuse_dataset and preserve_split:
            old_train_path = Path(reuse_dataset) / "train.jsonl"
            new_valid_path = out_dir / "valid.jsonl"
            if old_train_path.exists() and new_valid_path.exists():
                def _no_sys_key(msgs: list[dict]) -> str:
                    body = [m for m in msgs if m.get("role") != "system"]
                    return json.dumps(body, ensure_ascii=False, sort_keys=True)

                old_tr = {
                    _no_sys_key(json.loads(line)["messages"])
                    for line in old_train_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                }
                new_va = [
                    _no_sys_key(json.loads(line)["messages"])
                    for line in new_valid_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                overlap_cnt = sum(1 for k in new_va if k in old_tr)
                mdata.setdefault("split_integrity", {})["valid_overlap_with_reuse_train"] = overlap_cnt
        if mdata.get("relation_refresh") and mdata.get("knowledge_thin"):
            mdata["relation_refresh"]["kept_after_thin"] = mdata["knowledge_thin"].get(
                "pinned_relations"
            )
        if kept_articles:
            def _nosys(msgs: list[dict]) -> str:
                return json.dumps(
                    [m for m in msgs if m.get("role") != "system"],
                    ensure_ascii=False,
                    sort_keys=True,
                )

            fam_by_nosys = {
                _nosys(s["messages"]): (
                    (s.get("meta") or {}).get("parent") or articles.draft_id(s)
                )
                for s in kept_articles
            }
            tr_fams = {
                fam_by_nosys[k]
                for line in (out_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip() and (k := _nosys(json.loads(line)["messages"])) in fam_by_nosys
            }
            va_fams = {
                fam_by_nosys[k]
                for line in (out_dir / "valid.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip() and (k := _nosys(json.loads(line)["messages"])) in fam_by_nosys
            }
            mdata.setdefault("article_stats", {}).update(
                {
                    "train_families": len(tr_fams),
                    "valid_families": len(va_fams),
                    "family_leakage": len(tr_fams & va_fams),
                }
            )
            if articles.TRAIN_CONFIG.exists():
                try:
                    train_cfg = load_yaml(articles.TRAIN_CONFIG)
                    counter = articles.training_token_counter(train_cfg["base_model"])
                    sizes = [counter(s["messages"]) for s in kept_articles]
                    max_seq = train_cfg["max_seq_length"]
                    if max(sizes) > max_seq:
                        typer.secho(
                            f"错误：落盘文章样本最大长度 {max(sizes)} 超出 max_seq_length={max_seq}",
                            fg="red",
                        )
                        raise typer.Exit(1)
                    mdata["article_stats"]["token_lengths"] = {
                        "min": min(sizes),
                        "median": median(sizes),
                        "max": max(sizes),
                    }
                except typer.Exit:
                    raise
                except Exception as exc:
                    typer.secho(f"提示：跳过落盘 token 复算（{exc}）", fg="yellow")
        manifest_path.write_text(json.dumps(mdata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    typer.echo(f"数据集 {result['dataset_id']}：train {result['train']} / "
               f"valid {result['valid']}  分布 {result['counts']}")


@app.command("train")
def train(
    config: str = typer.Option(..., "--config", help="训练配置 yaml"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """本机 MLX QLoRA 训练。"""
    from .train.mlx_train import run_training

    result = run_training(config, artifacts)
    typer.echo(
        f"exp_id={result['exp_id']}  退出码 {result['returncode']}  "
        f"耗时 {result['duration_s']}s  日志 {result['log']}"
    )


@eval_cases_app.command("review")
def eval_cases_review(
    file: str = typer.Argument(..., help="候选用例 JSONL"),
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """逐条核对候选用例：输入行号查看问题与 gold 条款，标记 confirmed。"""
    import json as _json

    from .kb.store import get_clause_by_id, get_document, open_kb

    path = Path(file)
    rows = [
        _json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        row.setdefault("confirmed", False)

    kb_path = _resolve_cli_kb(kb_version, artifacts=artifacts)
    conn = open_kb(kb_path, read_only=True)

    def save() -> None:
        path.write_text(
            "".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )

    def _format_clause_ref(cid: str) -> str:
        clause = get_clause_by_id(conn, cid)
        doc = get_document(conn, clause.doc_id) if clause else None
        if clause and doc:
            return f"{doc.title}（{doc.version_label or '无版本'}）{clause.number_text} [{cid}]"
        return f"{cid}（未在库中找到）"

    def show(idx: int) -> None:
        row = rows[idx]
        source = row.get("source") or "manual"
        typer.echo(
            f"\n[{idx + 1}/{len(rows)}] {row['case_id']} "
            f"{row['category']}（source={source}，confirmed={row['confirmed']}）"
        )
        if "message" in row["input"]:
            typer.echo(f"  问题: {row['input']['message']}")
        for i, msg in enumerate(row["input"].get("script", []), 1):
            typer.echo(f"  第{i}轮: {msg}")
        gold = row.get("gold") or {}
        if gold.get("intent"):
            typer.echo(f"  预期意图: {gold['intent']}")
        for i, v in enumerate(gold.get("violations", []), 1):
            actor = v.get("actor", "")
            conduct = v.get("conduct", "")
            header = f"  违法行为[{i}] 主体={actor}"
            if conduct:
                header += f"｜行为={conduct}"
            typer.echo(header)
            if v.get("clauses"):
                refs = "；".join(_format_clause_ref(cid) for cid in v["clauses"])
                typer.echo(f"    适用条款: {refs}")
            if v.get("liability"):
                refs = "；".join(_format_clause_ref(cid) for cid in v["liability"])
                typer.echo(f"    法律责任: {refs}")
        for cid in gold.get("clauses", []):
            clause = get_clause_by_id(conn, cid)
            doc = get_document(conn, clause.doc_id) if clause else None
            if clause and doc:
                typer.echo(f"  gold: {doc.title}（{doc.version_label or '无版本'}）"
                           f"{clause.number_text}")
                typer.echo(f"        {clause.text}")
            else:
                typer.echo(f"  gold: {cid}（未在库中找到）")
        for i, line in enumerate(gold.get("rubric", []), 1):
            typer.echo(f"  rubric[{i}]: {line}")
        for pn in gold.get("protected_names", []):
            typer.echo(f"  保护名称: {pn['name']}（第 {pn['turn']} 轮用户提供）")
        exp = gold.get("expect_articles")
        if exp is not None:
            if isinstance(exp, list):
                parts = "；".join(
                    f"第{i + 1}轮{n}篇" for i, n in enumerate(exp) if n is not None
                )
                typer.echo(f"  期望篇数: {parts}")
            else:
                typer.echo(f"  期望篇数: {exp}")
        if gold.get("should_refuse"):
            typer.echo("  预期: 应拒答")

    typer.echo(
        f"共 {len(rows)} 条。用法：行号=查看并标记；行号 t/f=直接标记；"
        "q=退出。标记时回车=true，n=false，s=跳过"
    )
    while True:
        try:
            line = input("\n行号> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("q", "quit", "exit"):
            break
        if not line:
            continue
        parts = line.split()
        try:
            idx = int(parts[0]) - 1
        except ValueError:
            typer.echo("请输入行号（1 起始），或 q 退出")
            continue
        if not 0 <= idx < len(rows):
            typer.echo(f"超出范围（1–{len(rows)}）")
            continue
        show(idx)
        verdict = parts[1] if len(parts) > 1 else None
        if verdict is None:
            try:
                verdict = input("confirmed? [Y/n/s] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
        if verdict in ("", "y", "t", "true", "1"):
            rows[idx]["confirmed"] = True
        elif verdict in ("n", "f", "false", "0"):
            rows[idx]["confirmed"] = False
        else:
            typer.echo("已跳过，未修改")
            continue
        save()
        done = sum(1 for row in rows if row["confirmed"])
        typer.echo(f"→ confirmed={rows[idx]['confirmed']}（累计 true {done}/{len(rows)}）")

    conn.close()
    typer.echo(
        f"\n已保存 {path}。审完后运行："
        f"uv run tu eval cases promote {path}"
    )


@eval_cases_app.command("promote")
def eval_cases_promote(
    file: str = typer.Argument(..., help="已核对的候选用例 JSONL"),
    out: str = typer.Option(
        "eval/cases/v1/reviewed.jsonl", help="输出的正式评测集 JSONL"
    ),
) -> None:
    """把 confirmed=true 的候选用例写入 v1（保留 manual/public_case，其余标为 synthetic_reviewed）。"""
    import json as _json

    rows = [
        _json.loads(line)
        for line in Path(file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kept = []
    for row in rows:
        if not row.get("confirmed"):
            continue
        if row.get("source") not in {"manual", "public_case", "synthetic_reviewed"}:
            row["source"] = "synthetic_reviewed"
        row.pop("confirmed", None)
        kept.append(row)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in kept),
        encoding="utf-8",
    )
    typer.echo(f"已写入 {len(kept)} 条正式用例 → {out_path}")


@eval_app.command("run")
def eval_run(
    cases: str = typer.Option(..., "--cases", help="评测集目录或 jsonl"),
    kb_version: str | None = typer.Option(None, help="知识库版本（覆盖 app.yaml 的 kb.version）"),
    exp: str | None = typer.Option(None, "--exp", help="实验 ID（记录用）"),
    no_system_prompt: bool = typer.Option(
        False, "--no-system-prompt",
        help="评测时不发送 system prompt（对照实验用）",
    ),
    config: str = typer.Option("configs/app.yaml"),
    artifacts: str | None = typer.Option(
        None, help="产物目录（默认取 app.yaml 的 paths.artifacts 或 artifacts）"
    ),
) -> None:
    """运行评测（temperature=0，不调用外部服务）。"""
    from .chat.assistant import session_config_from
    from .config import get, load_app_config, resolve_model_name
    from .eval.runner import run_eval
    from .kb.store import normalize_artifacts_dir

    cfg = load_app_config(config)
    eff_artifacts = str(normalize_artifacts_dir(artifacts, config=cfg))
    kb_path = _resolve_cli_kb(kb_version, config=cfg, artifacts=eff_artifacts)
    result = run_eval(
        cases_path=cases,
        kb_path=kb_path,
        endpoint=get(cfg, "runtime.model_endpoint"),
        allowed_hosts=get(cfg, "runtime.allowed_hosts"),
        model_name=resolve_model_name(cfg, eff_artifacts),
        artifacts_dir=eff_artifacts,
        exp_id=exp,
        session_config=session_config_from(cfg, use_system_prompt=not no_system_prompt),
    )
    typer.echo(f"run_id={result['run_id']}  用例 {result['cases']} 条 → {result['dir']}")
    if result["gold_issues"]:
        typer.secho(
            f"注意：{len(result['gold_issues'])} 个 gold 条款在知识库中不存在",
            fg="yellow",
        )


def _is_in_existing_eval_subdir(out: str | Path, artifacts: str | Path) -> bool:
    out_path = Path(out).resolve()
    eval_root = (Path(artifacts) / "eval").resolve()
    if out_path.parent == eval_root and out_path.exists():
        return True
    return eval_root in out_path.parents and any(
        parent.parent == eval_root and parent.exists() for parent in out_path.parents
    )


@eval_app.command("report")
def eval_report(
    run_id: str = typer.Argument(..., help="评测 run ID（artifacts/eval/<run_id>）"),
    reviews: str | None = typer.Option(
        None,
        "--reviews",
        help="人工评审 CSV 路径（格式见 eval/review-template.csv）",
    ),
    out: str | None = typer.Option(
        None,
        "--out",
        help="输出 Markdown 路径（不传则输出到 stdout；禁止覆盖已有 run 目录下的 report.md）",
    ),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """只读读取已有评测 run 生成完整报告（可汇总人工评审 CSV，不覆盖历史产物）。"""
    from .eval.report import ReportError, render_run_report

    if out is not None and _is_in_existing_eval_subdir(out, artifacts):
        out_path = Path(out).resolve()
        typer.secho(
            f"拒绝写入已有历史评测目录：{out_path}（请指定外部输出路径或不传 --out）",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)

    try:
        report_md = render_run_report(artifacts, run_id, reviews_path=reviews)
    except ReportError as e:
        typer.secho(f"报告生成失败：{e}", fg="red", err=True)
        raise typer.Exit(2) from e

    if out is None:
        typer.echo(report_md, nl=False)
    else:
        target = Path(out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(report_md, encoding="utf-8")
        except OSError as e:
            typer.secho(f"写入报告失败（{target}）：{e}", fg="red", err=True)
            raise typer.Exit(2) from e
        typer.echo(f"已写入报告 → {target}")


@eval_app.command("compare")
def eval_compare(
    runs: Annotated[list[str], typer.Argument(help="两个及以上 run ID（首项为基准）")],
    sc016: bool = typer.Option(
        False, "--sc016", help="按 spec SC-016 判定（POC 验收/回归门槛）"
    ),
    sc015: bool = typer.Option(
        False, "--sc015", help="按 spec SC-015 判定同模型重复评测稳定性（波动 ≤ 2.0 pp）"
    ),
    reviews: str | None = typer.Option(
        None, "--reviews", help="人工评审 CSV 路径（用于对比 SC-009 / SC-010）"
    ),
    out: str | None = typer.Option(
        None,
        "--out",
        help="输出 compare.md 路径（不传则输出到 stdout；禁止写入已有 artifacts/eval 子目录）",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="落盘至独立目录 artifacts/eval/compare-<ts>/（含 compare.md 与 manifest.json）",
    ),
    artifacts: str = typer.Option("artifacts", help="产物目录"),
) -> None:
    """对比多个评测 run（FR-035）；支持 --sc015 稳定性校验与 --sc016 POC 验收判定。"""
    from .eval.compare import (
        CompareError,
        _kb_path_from_manifest,
        align_cases,
        align_general_cases,
        check_general_comparable,
        comparability_issues,
        compare_runs,
        evaluate_sc015,
        load_doc_index,
        load_run,
        render_compare_markdown,
        role_issues,
        same_system_issues,
        save_compare_artifact,
    )
    from .eval.compare import (
        sc016 as run_sc016,
    )

    if sc016 and sc015:
        typer.echo("输入错误：--sc016 与 --sc015 不能同时使用", err=True)
        raise typer.Exit(2)
    if sc016 and (out is not None or save or reviews is not None):
        typer.echo("输入错误：--sc016 不支持与 --out / --save / --reviews 同时使用", err=True)
        raise typer.Exit(2)
    if out is not None and save:
        typer.echo("输入错误：--out 与 --save 不能同时使用", err=True)
        raise typer.Exit(2)

    if sc016:
        if len(runs) != 2:
            typer.echo("--sc016 需要恰好两个 run ID：<基座> <自训>", err=True)
            raise typer.Exit(2)
        try:
            base, trained = load_run(artifacts, runs[0]), load_run(artifacts, runs[1])
            issues = comparability_issues(base, trained) + role_issues(base, trained)
            aligned = align_cases(base, trained)
            docs = load_doc_index(_kb_path_from_manifest(base.manifest, artifacts))
            res = run_sc016(aligned, docs)
        except CompareError as e:
            typer.echo(f"输入错误：{e}", err=True)
            raise typer.Exit(2) from e
        if issues:
            for i in issues:
                typer.echo(f"无法确认：{i}", err=True)
            typer.secho("总判定：无法判定（输入可比性无法确认）", fg="red", err=True)
            raise typer.Exit(1)

        bm = (base.manifest.get("config") or {}).get("model")
        tm = (trained.manifest.get("config") or {}).get("model")
        typer.echo(f"SC-016 判定（{res.n} 条 clause_id 用例）")
        typer.echo(f"  基座 run：{base.run_id}（model={bm}）")
        typer.echo(f"  自训 run：{trained.run_id}（model={tm}）")

        def mark(ok: bool | None) -> str:
            return "PASS" if ok else ("无法判定" if ok is None else "FAIL")

        typer.echo(
            f"  ① 条级命中：基座 {res.cond1_base}/{res.n}，自训 {res.cond1_trained}/{res.n}；"
            f"Fisher 双侧 p={res.cond1_p:.3g} → {mark(res.cond1_ok)}"
        )
        typer.echo(
            f"  ② 款/项级精确命中：{res.cond2_trained}/{res.n} = "
            f"{res.cond2_ratio:.1%}（阈值 ≥10%）→ {mark(res.cond2_ok)}"
        )
        if res.cond3_ok is None:
            typer.echo("  ③ 基座从未识别的文件子集为空 → 无法判定")
        else:
            typer.echo(
                f"  ③ 基座从未识别的文件子集（{res.subset_n} 题）：文件命中 基座 "
                f"{res.cond3_base}/{res.subset_n}，自训 {res.cond3_trained}/{res.subset_n}；"
                f"p={res.cond3_p:.3g} → {mark(res.cond3_ok)}"
            )
        if res.passed:
            typer.secho("总判定：PASS", fg="green")
            raise typer.Exit(0)
        typer.secho("总判定：FAIL", fg="red")
        raise typer.Exit(1)

    # 通用多 run 对比 / --sc015 重复评测稳定性校验（T062）
    if len(runs) < 2:
        typer.echo("输入错误：至少需要 2 个 run ID 进行对比", err=True)
        raise typer.Exit(2)
    if out is not None and _is_in_existing_eval_subdir(out, artifacts):
        out_path = Path(out).resolve()
        typer.secho(
            f"拒绝写入已有历史评测目录：{out_path}（请指定外部输出路径或使用 --save）",
            fg="red",
            err=True,
        )
        raise typer.Exit(2)

    try:
        loaded = [load_run(artifacts, rid) for rid in runs]
        issues, notes = check_general_comparable(loaded)
        if sc015:
            issues = issues + same_system_issues(loaded)
        align_general_cases(loaded)
    except CompareError as e:
        typer.echo(f"输入错误：{e}", err=True)
        raise typer.Exit(2) from e

    if issues:
        for i in issues:
            typer.echo(f"无法确认：{i}", err=True)
        msg = (
            "总判定：无法判定（输入可比性或系统版本无法确认）"
            if sc015
            else "无法确认对比可比性（存在缺失字段或无法核对的评测集来源）"
        )
        typer.secho(msg, fg="red", err=True)
        raise typer.Exit(1)

    try:
        comparison = compare_runs(loaded, reviews_path=reviews, notes=notes)
    except CompareError as e:
        typer.echo(f"输入错误：{e}", err=True)
        raise typer.Exit(2) from e

    sc015_res = evaluate_sc015(comparison) if sc015 else None
    compare_md = render_compare_markdown(comparison, sc015_result=sc015_res)

    if save:
        try:
            out_dir = save_compare_artifact(
                artifacts, comparison, compare_md, sc015_result=sc015_res
            )
        except OSError as e:
            typer.secho(f"保存对比报告失败：{e}", fg="red", err=True)
            raise typer.Exit(2) from e
        typer.echo(f"已保存对比报告 → {out_dir / 'compare.md'}")
    elif out is not None:
        target = Path(out)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(compare_md, encoding="utf-8")
        except OSError as e:
            typer.secho(f"写入对比报告失败（{target}）：{e}", fg="red", err=True)
            raise typer.Exit(2) from e
        typer.echo(f"已写入对比报告 → {target}")
    else:
        typer.echo(compare_md, nl=False)

    if sc015_res is not None:
        if sc015_res.passed is True:
            if save or out is not None:
                typer.secho("SC-015 总判定：PASS", fg="green")
            raise typer.Exit(0)
        if save or out is not None:
            verdict = "无法判定（无有效指标）" if sc015_res.passed is None else "FAIL"
            typer.secho(f"SC-015 总判定：{verdict}", fg="red")
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("chat")
def chat(
    config: str = typer.Option("configs/app.yaml"),
    artifacts: str | None = typer.Option(
        None, help="产物目录（默认取 app.yaml 的 paths.artifacts 或 artifacts）"
    ),
    kb_version: str | None = typer.Option(None, help="知识库版本（覆盖 app.yaml 的 kb.version）"),
) -> None:
    """命令行多轮对话；/save <path> 保存最后一轮为 .md，/new 新会话，/quit 退出。"""
    from .chat.assistant import TrainedAssistant, session_config_from
    from .config import get, load_app_config, resolve_model_name
    from .kb.store import KBError, normalize_artifacts_dir, open_kb
    from .runtime.client import ModelClient

    cfg = load_app_config(config)
    if hasattr(TrainedAssistant, "from_config"):
        try:
            assistant = TrainedAssistant.from_config(
                config,
                kb_version=kb_version,
                artifacts_dir=artifacts,
            )
        except KBError as e:
            typer.secho(str(e), fg="red", err=True)
            raise typer.Exit(2) from e
        close_cb = assistant.close_kb
        active_kb_ver = assistant.kb_version
    else:
        eff_artifacts = str(normalize_artifacts_dir(artifacts, config=cfg))
        kb_path = _resolve_cli_kb(kb_version, config=cfg, artifacts=eff_artifacts)
        conn = open_kb(kb_path, read_only=True)
        try:
            client = ModelClient(
                get(cfg, "runtime.model_endpoint"),
                get(cfg, "runtime.allowed_hosts"),
                model=resolve_model_name(cfg, eff_artifacts),
            )
            assistant = TrainedAssistant(client, conn)
        except Exception:
            conn.close()
            raise
        close_cb = conn.close
        active_kb_ver = kb_path.stem

    try:
        scfg = session_config_from(cfg)
        sid = assistant.new_session(scfg)
        typer.echo(
            f"进入对话（知识库：{active_kb_ver}；/save <路径> 保存，/new 新会话，/quit 退出）"
        )
        while True:
            try:
                msg = typer.prompt("你")
            except (EOFError, KeyboardInterrupt):
                break
            if not msg.strip():
                continue
            if msg.startswith("/save"):
                parts = msg.split(maxsplit=1)
                if len(parts) < 2:
                    typer.echo("用法：/save <路径.md>")
                    continue
                Path(parts[1]).write_text(
                    assistant.export_markdown(sid), encoding="utf-8"
                )
                typer.echo(f"已保存到 {parts[1]}")
                continue
            if msg == "/new":
                assistant.close(sid)
                sid = assistant.new_session(scfg)
                typer.echo("新会话")
                continue
            if msg in {"/quit", "/exit"}:
                break
            reply = assistant.send(sid, msg)
            typer.echo(f"\n{reply.content}\n")
        assistant.close(sid)
    finally:
        close_cb()


if __name__ == "__main__":
    app()
