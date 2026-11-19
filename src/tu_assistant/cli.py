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


def _latest_kb(artifacts_dir: str) -> Path:
    files = sorted(Path(artifacts_dir, "kb").glob("kb-*.sqlite"))
    if not files:
        typer.secho("没有知识库版本，请先运行 tu kb import", fg="red")
        raise typer.Exit(1)
    return files[-1]


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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    c = get_clause_by_id(conn, clause_id)
    doc = get_document(conn, c.doc_id) if c else None
    conn.close()
    if not c or not doc:
        typer.secho("未找到该条款", fg="red")
        raise typer.Exit(1)
    typer.echo(f"{doc.title}（{doc.version_label or '无版本'}）{c.number_text}\n{c.text}\n")


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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)

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
    """model_name 为 default 时，读取 serve model 记录的当前模型。"""
    from .config import get

    name = get(cfg, "runtime.model_name", "default")
    if name != "default":
        return name
    cur = Path(artifacts, "serve", "current.json")
    if cur.exists():
        return json.loads(cur.read_text(encoding="utf-8"))["model"]
    return name


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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    llm = from_config(load_synth_config(synth_config))
    result = generate_candidates(conn, llm, n=n)
    conn.close()
    typer.echo(f"候选用例 {result['written']} 条 → {result['path']}")


@synth_app.command("sft")
def synth_sft(
    kb_version: str | None = typer.Option(None),
    artifacts: str = typer.Option("artifacts"),
    synth_config: str = typer.Option("configs/synth.yaml"),
    eval_cases: str = typer.Option("eval/cases", help="评测集目录（去重用）"),
    skip_llm: bool = typer.Option(False, help="只用确定性样本（调试用）"),
    reuse_dataset: str | None = typer.Option(
        None, help="复用已有 train/valid 中的样本，只补新生成部分"
    ),
    reuse_only: bool = typer.Option(
        False, "--reuse-only", help="只重建数据集，不再生成任何新样本"
    ),
) -> None:
    """生成 SFT 训练样本并构建数据集。"""
    from .config import load_synth_config
    from .eval.cases import eval_questions, load_cases
    from .kb.store import open_kb
    from .synth import consult, dialogs, general, knowledge, refusal
    from .synth.check import CheckStats, check_sample
    from .synth.llm import from_config
    from .train.dataset import (
        balance_by_doc,
        dedup_against_eval,
        load_message_samples,
        write_dataset,
    )

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    if reuse_only and not reuse_dataset:
        typer.secho("--reuse-only 需要同时提供 --reuse-dataset", fg="red")
        raise typer.Exit(1)

    conn = open_kb(kb_path)
    cfg = load_synth_config(synth_config)
    llm = None if skip_llm else from_config(cfg)

    if reuse_dataset:
        samples = load_message_samples(reuse_dataset, conn)
        typer.echo(f"复用已有样本 {len(samples)} 条 → {reuse_dataset}")
    else:
        samples = knowledge.generate(conn, llm, cfg)
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
    kept = []
    for s in samples:
        last = s["messages"][-1]
        requires_citation = s.get("meta", {}).get("type") not in {
            "refusal", "general",
        }
        if last["role"] == "assistant" and not check_sample(
            last["content"],
            conn,
            stats,
            require_citation=requires_citation,
            expected_clause_ids=set(s.get("meta", {}).get("clause_ids", [])),
        ):
            continue
        kept.append(s)
    conn.close()
    typer.echo(f"样本检查：{stats.kept} 保留 / {stats.dropped} 丢弃 {stats.reasons}")

    # 与评测集去重
    cases_dir = Path(eval_cases)
    questions = eval_questions(load_cases(cases_dir)) if cases_dir.exists() else []
    kept, dropped = dedup_against_eval(kept, questions)
    if dropped:
        typer.echo(f"与评测集去重：剔除 {len(dropped)} 条")

    kept = balance_by_doc(kept, seed=cfg.get("seed", 42))
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
    result = write_dataset(
        kept, dataset_id, Path(artifacts, "datasets"),
        kb_version=kb_path.stem,
        generator=generator,
        eval_set_version="v1",
        seed=cfg.get("seed", 42),
        train_oversample=cfg.get("train_oversample", {}),
        add_system_prompt=cfg.get("add_system_prompt", False),
        knowledge_max=knowledge_max,
    )
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

    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)

    def save() -> None:
        path.write_text(
            "".join(_json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )

    def show(idx: int) -> None:
        row = rows[idx]
        typer.echo(
            f"\n[{idx + 1}/{len(rows)}] {row['case_id']} "
            f"{row['category']}（confirmed={row['confirmed']}）"
        )
        if "message" in row["input"]:
            typer.echo(f"  问题: {row['input']['message']}")
        for i, msg in enumerate(row["input"].get("script", []), 1):
            typer.echo(f"  第{i}轮: {msg}")
        for cid in row.get("gold", {}).get("clauses", []):
            clause = get_clause_by_id(conn, cid)
            doc = get_document(conn, clause.doc_id) if clause else None
            if clause and doc:
                typer.echo(f"  gold: {doc.title}（{doc.version_label or '无版本'}）"
                           f"{clause.number_text}")
                typer.echo(f"        {clause.text}")
            else:
                typer.echo(f"  gold: {cid}（未在库中找到）")
        for i, line in enumerate(row.get("gold", {}).get("rubric", []), 1):
            typer.echo(f"  rubric[{i}]: {line}")
        for pn in row.get("gold", {}).get("protected_names", []):
            typer.echo(f"  保护名称: {pn['name']}（第 {pn['turn']} 轮用户提供）")
        exp = row.get("gold", {}).get("expect_articles")
        if exp is not None:
            if isinstance(exp, list):
                parts = "；".join(
                    f"第{i + 1}轮{n}篇" for i, n in enumerate(exp) if n is not None
                )
                typer.echo(f"  期望篇数: {parts}")
            else:
                typer.echo(f"  期望篇数: {exp}")
        if row.get("gold", {}).get("should_refuse"):
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
    """把 confirmed=true 的候选用例写入 v1，并标记 source=synthetic_reviewed。"""
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
    kb_version: str | None = typer.Option(None),
    exp: str | None = typer.Option(None, "--exp", help="实验 ID（记录用）"),
    no_system_prompt: bool = typer.Option(
        False, "--no-system-prompt",
        help="评测时不发送 system prompt（对照实验用）",
    ),
    config: str = typer.Option("configs/app.yaml"),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """运行评测（temperature=0，不调用外部服务）。"""
    from .chat.assistant import SessionConfig
    from .config import get, load_app_config
    from .eval.runner import run_eval

    cfg = load_app_config(config)
    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    result = run_eval(
        cases_path=cases,
        kb_path=kb_path,
        endpoint=get(cfg, "runtime.model_endpoint"),
        allowed_hosts=get(cfg, "runtime.allowed_hosts"),
        model_name=_model_name(cfg, artifacts),
        artifacts_dir=artifacts,
        exp_id=exp,
        session_config=SessionConfig(use_system_prompt=not no_system_prompt),
    )
    typer.echo(f"run_id={result['run_id']}  用例 {result['cases']} 条 → {result['dir']}")
    if result["gold_issues"]:
        typer.secho(
            f"注意：{len(result['gold_issues'])} 个 gold 条款在知识库中不存在",
            fg="yellow",
        )


@eval_app.command("compare")
def eval_compare(
    runs: Annotated[list[str], typer.Argument(help="两个 run ID：<基座> <自训>")],
    sc016: bool = typer.Option(
        False, "--sc016", help="按 spec SC-016 判定（POC 验收/回归门槛）"
    ),
    artifacts: str = typer.Option("artifacts"),
) -> None:
    """对比两个评测 run；--sc016 输出 SC-016 判定（通用对比由 T062 实现）。"""
    from .eval.compare import (
        CompareError,
        align_cases,
        comparability_issues,
        load_doc_index,
        load_run,
        resolve_kb_path,
        role_issues,
    )
    from .eval.compare import (
        sc016 as run_sc016,
    )

    if not sc016:
        typer.echo("目前仅支持 --sc016；通用多 run 对比由 T062 实现", err=True)
        raise typer.Exit(2)
    if len(runs) != 2:
        typer.echo("--sc016 需要恰好两个 run ID：<基座> <自训>", err=True)
        raise typer.Exit(2)
    try:
        base, trained = load_run(artifacts, runs[0]), load_run(artifacts, runs[1])
        issues = comparability_issues(base, trained) + role_issues(base, trained)
        aligned = align_cases(base, trained)
        docs = load_doc_index(resolve_kb_path(base.manifest, artifacts))
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


@app.command("chat")
def chat(
    config: str = typer.Option("configs/app.yaml"),
    artifacts: str = typer.Option("artifacts"),
    kb_version: str | None = typer.Option(None),
) -> None:
    """命令行多轮对话；/save <path> 保存最后一轮为 .md，/new 新会话，/quit 退出。"""
    from .chat.assistant import SessionConfig, TrainedAssistant
    from .config import get, load_app_config
    from .kb.store import open_kb
    from .runtime.client import ModelClient

    cfg = load_app_config(config)
    kb_path = (
        Path(artifacts, "kb", f"{kb_version}.sqlite")
        if kb_version
        else _latest_kb(artifacts)
    )
    conn = open_kb(kb_path)
    client = ModelClient(
        get(cfg, "runtime.model_endpoint"),
        get(cfg, "runtime.allowed_hosts"),
        model=_model_name(cfg, artifacts),
    )
    assistant = TrainedAssistant(client, conn)
    scfg = SessionConfig(
        max_questions_per_turn=get(cfg, "session.max_questions_per_turn", 5),
        default_article_count=get(cfg, "session.default_article_count", 3),
        max_article_count=get(cfg, "session.max_article_count", 10),
    )
    sid = assistant.new_session(scfg)
    typer.echo("进入对话（/save <路径> 保存，/new 新会话，/quit 退出）")
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
    conn.close()


if __name__ == "__main__":
    app()
