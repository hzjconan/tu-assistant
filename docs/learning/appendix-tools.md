# 附录：uv 与命令行工具的实现

本文解释两个和训练主线无关、但天天在用的东西：包管理器 `uv`，以及
`tu kb relations review` 这个交互式核对工具是怎么实现的。

## [LA.1] uv 是什么

`uv` 是 Astral 公司（就是写 ruff 的那家）用 Rust 写的 Python 包管理器。
一个工具顶替了传统组合里的好几个角色：

| 传统工具 | 干什么 | uv 对应 |
|---|---|---|
| `pip` | 装包 | `uv add` / `uv pip install` |
| `venv` | 建虚拟环境 | `uv` 自动维护 `.venv/` |
| `pyenv` | 装/切换 Python 版本 | `uv python` |
| `pip-tools` | 锁定依赖版本 | `uv.lock` |

选它的原因：快（Rust 实现，装包比 pip 快一个数量级）、依赖解析可靠、
lock 文件跨平台一致——你在自己机器上 `uv sync` 得到的环境和我这边完全相同。

## [LA.2] 本项目里 uv 的运转方式

涉及四个文件/目录：

- `pyproject.toml`：声明项目名、依赖（`dependencies`）、命令入口
  （`[project.scripts]` 里 `tu = "tu_assistant.cli:app"` 定义了 `tu` 命令）。
- `.python-version`：钉死 Python 版本（3.12）。
- `uv.lock`：每个依赖的精确版本+哈希，相当于"环境快照"，已提交进 git。
- `.venv/`：实际环境目录，已 gitignore。

最常用的命令是 `uv run`：

```bash
uv run tu kb list        # 在 .venv 里运行 tu 命令
uv run pytest            # 同理，跑测试
uv run ruff check .      # 同理，跑 lint
```

`uv run` 的好处是**不用手动激活虚拟环境**：它自动找到项目的 `.venv`，
发现依赖有变动还会先同步再执行。所以本项目所有命令都以 `uv run` 开头。

装新依赖用 `uv add <包>`——它会同时改 `pyproject.toml`、重装环境、更新
`uv.lock`，三步一次完成，不要直接 `pip install`。

顺带解释目录命名：`tu-assistant/`（仓库名）和 `src/tu_assistant/`（包名）
不是重复，是两套规则。仓库名是给人看的文件夹名，惯例用 `-`；包名是
`import` 时写的 Python 标识符，**不允许有 `-`**（会被当成减法），所以
必须用 `_`。生态通行约定：发行名 `-`、包名 `_`。外面多套一层 `src/`
也是故意的（"src layout"）：这样根目录下直接 `import tu_assistant` 会
失败，逼着测试必须走 `uv run` 用**真正安装后的包**，提前暴露打包问题，
而不是拿源码目录蒙混过关。

## [LA.3] relations review 工具的流程定位

条款关联的人工确认分三步，review 是中间那步：

```
extract（规则抽取）→ pending.jsonl → review（人工标记）→ confirm（入库）
   程序自动            68 行候选        你看条款定真伪        只导入 confirmed=true
```

- `extract`：`src/tu_assistant/cli.py:131`，调用
  `kb/relations.py:extract_relations()` 用正则扫条款原文，生成
  `relations_pending.jsonl`，每行 `confirmed: false`。
- `review`：`cli.py:219`，就是现在用的交互式核对。
- `confirm`：`cli.py:176`，把 `confirmed: true` 的行写入 SQLite 的
  `clause_relations` 表。

## [LA.4] review 命令的实现结构

入口是 `src/tu_assistant/cli.py` 里的 `relations_review()`（约 219 行起），
内部就四个部分，都是普通 Python，没有框架魔法：

1. **加载**：把 jsonl 每行 `json.loads` 成 dict 存进 `rows` 列表。
   行号 = 列表下标 + 1，所以你输入的行号直接对应文件里的行。
2. **`save()`**：把 `rows` 整体写回 jsonl。每次标记后立即保存，中途
   Ctrl+C 退出也不丢已标的结果。写回时只改 `confirmed` 字段，其他字段原样保留。
3. **`show(idx)`**：打印一条候选的 from/to。对 `clause_id` 调两个函数：
   - `kb/store.py:234 get_clause_by_id()`——按 clause_id 查条款行；
   - `kb/store.py:188 get_document()`——按 `doc_id` 查文件标题和版本。
   clause_id 里那段哈希（如 `3296db5b22b8ea1d`）就是 doc_id，由
   `store.py:76 doc_id_for()` 对"标题|版本"做 SHA-256 取前 16 位生成。
4. **主循环**：`input()` 读一行 → 解析"行号 [t/f]" → `show()` →
   没有第二参数时再 `input()` 追问 `confirmed? [Y/n/s]` → 改 `rows` → `save()`。

Typer 的角色很轻：`@relations_app.command("review")` 装饰器把函数注册成
`tu kb relations review` 子命令，函数的参数声明（`file: str = typer.Argument(...)`）
自动变成命令行参数解析，不需要手写 argparse。

这里容易混淆"谁提供了什么"，按层分：

- **Python 语言**：`def`、装饰器 `@xxx`、类型标注 `str | None`；
- **Typer（第三方库，见 `pyproject.toml` 依赖）**：`typer.Typer()`、
  `Argument`/`Option`、`echo`——它的思路是用类型标注声明命令行界面，
  底层是更老牌的 Click；
- **Python 打包标准**：`pyproject.toml` 的 `[project.scripts]` 声明
  `tu = "tu_assistant.cli:app"`，uv/pip/hatch 都按这个规范在 `.venv/bin/`
  里生成 `tu` 可执行文件；
- **uv**：只负责装依赖（含 Typer）、生成入口、在虚拟环境里运行它。
  换成 pip+venv 手动管理，`cli.py` 一个字符都不用改。

## [LA.5] 可以继续问的问题

- uv 的依赖解析（resolution）和 pip 有什么区别？为什么快？
- lock 文件里记了什么？换台机器 `uv sync` 怎么复现环境？
- `input()` 循环还能怎么扩展——比如加"上一条/下一条"翻页、批量标记？
- Typer/Click 是怎么把函数签名变成命令行界面的？
- 如果候选有 6800 条而不是 68 条，这个工具该改哪里？（翻页、过滤、抽样）
