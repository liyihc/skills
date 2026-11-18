#!/usr/bin/env python3
"""查询 opencode 子会话的上下文占用（只读，不改动任何会话数据）。

上下文 = 该会话最后一条带 tokens 的 assistant 消息的
         input + cache.read + cache.write + output + reasoning，
即真正占用模型窗口的 token 数；百分比按该会话自己模型的 limit.context 折算。

用法：
    context_usage.py --candidates                    # 能接手实现的候选，上下文升序
    context_usage.py --session <session-id>
    context_usage.py --children-of [<parent-id>]     # 省略父 id 时取 OPENCODE_SESSION_ID
    context_usage.py --children-of --table
    context_usage.py --session <id> --table

退出码：0 正常（含 unknown、无子会话）；1 参数/会话缺失；2 找不到库或库结构不兼容。
"""

import argparse
import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import unicodedata
from pathlib import Path

# 能改文件的工具动作。判定"这个子智能体能不能接手实现"时只看这几项，
# 别的动作（read/grep/shell 之类）与写代码无关。
WRITE_ACTIONS = ("edit", "write", "patch")


def utf8_pipe(stream):
    """管道输出统一按 UTF-8 编码，避免 Windows 控制台代码页把中文标题写坏。"""
    if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text, width):
    return text + " " * max(0, width - display_width(text))


def run_opencode(*args):
    """跑一次 opencode 子命令并返回 stdout；命令不可用时返回 None。"""
    try:
        proc = subprocess.run(
            ["opencode", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout


def debug_paths():
    """opencode debug paths 打印 data/cache/db 等绝对路径，省掉跨平台猜目录。"""
    raw = run_opencode("debug", "paths")
    if raw is None:
        return {}
    out = {}
    for line in raw.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[0]] = parts[1].strip()
    return out


def agent_writability():
    """agent id -> 能否改文件（True/False）。探测失败返回空 dict，含义是「不知道」。

    依据 `opencode debug agents` 的权限表判定，不写死 agent 名字：名字随配置变，
    权限才是同一件事的机读形式。opencode 的权限按「最后一条匹配的规则生效」求值：
    explore 的表先 `allow * *`、再 `deny * *`，之后只逐项放行 shell/grep/glob/read，
    没有重新放行 edit，所以它是只读的；general/build 的 `allow * *` 之后没有覆盖
    写操作的规则，所以可写。这里只取最后一条命中写操作的规则，resource 不细分
    （写操作对应的 resource 都是 `*`）。
    """
    raw = run_opencode("debug", "agents")
    if raw is None:
        return {}
    try:
        agents = json.loads(raw)
    except ValueError:
        return {}
    writability = {}
    for agent in agents if isinstance(agents, list) else []:
        agent_id = agent.get("id")
        if not agent_id:
            continue
        writable = False  # 没有任何规则放行写操作时，opencode 的默认效果是拒绝
        for rule in agent.get("permissions") or []:
            if rule.get("action") not in ("*",) + WRITE_ACTIONS:
                continue
            writable = rule.get("effect") in ("allow", "ask")  # ask 只是要确认，仍能写
        writability[agent_id] = writable
    return writability


def db_path(paths):
    if paths.get("db"):
        return paths["db"]
    data = paths.get("data") or os.path.join(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")),
        "opencode",
    )
    return os.path.join(data, "opencode.db")


def load_limits(paths):
    """(provider, model) -> limit.context，来源是 models.json 缓存。"""
    cache = paths.get("cache") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")),
        "opencode",
    )
    try:
        data = json.loads((Path(cache) / "models.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    limits = {}
    for provider_id, provider in data.items():
        for model_id, model in (provider.get("models") or {}).items():
            context = (model.get("limit") or {}).get("context")
            if context:
                limits[(provider_id, model_id)] = context
    return limits


def connect(path):
    # 只读 URI：父会话可能正在写库（WAL 模式），只读连接不会阻塞它，也不会改动数据
    uri = "file:" + Path(path).as_posix() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2)


def session_context(conn, session_id):
    """最后一条带 tokens 的 assistant 消息；运行中的会话可能还没有。"""
    for (raw,) in conn.execute(
        "select data from session_message"
        " where session_id=? and type='assistant' order by seq desc limit 200",
        (session_id,),
    ):
        try:
            tokens = json.loads(raw).get("tokens")
        except ValueError:
            continue
        if not tokens:
            continue
        cache = tokens.get("cache") or {}
        total = (
            tokens.get("input", 0)
            + cache.get("read", 0)
            + cache.get("write", 0)
            + tokens.get("output", 0)
            + tokens.get("reasoning", 0)
        )
        # 全零说明这一轮没有记账（流被中断等），不是"上下文为 0"，继续往前找
        if total == 0:
            continue
        return total
    return None


def session_record(conn, row, limits, writability=None):
    session_id, parent_id, title, agent, model_raw, busy, idle, updated = row
    status = "running" if busy and (not idle or idle < busy) else "idle"
    try:
        parsed = json.loads(model_raw) if model_raw else {}
    except ValueError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    model = parsed.get("id") or parsed.get("modelID")
    provider = parsed.get("providerID")

    context = session_context(conn, session_id)
    limit = limits.get((provider, model)) if model else None
    percent = round(context * 100 / limit, 1) if (context is not None and limit) else None
    writable = None if writability is None else writability.get(agent)

    # why 给父 agent 看：非空即视为不合格候选，不需要它自己再解释
    why = None
    if context is None:
        why = "running" if status == "running" else "no-tokens"
    elif not limit:
        why = "no-limit"
    elif writability is not None and writable is not True:
        why = "write-unknown" if writable is None else "read-only"

    return {
        "session_id": session_id,
        "parent_id": parent_id,
        "title": title,
        "agent": agent,
        "model": model,
        "status": status,
        "context": context,
        "limit": limit,
        "percent": percent,
        "writable": writable,
        "why": why,
        "time_updated": updated,
    }


def human_tokens(value):
    if value is None:
        return "?"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value / 1_000:.1f}k"


def print_table(records):
    if not records:
        return
    header = ("SESSION", "AGENT", "STATUS", "CONTEXT", "PCT", "WHY", "TITLE")
    rows = [
        (
            r["session_id"],
            r["agent"] or "-",
            r["status"],
            human_tokens(r["context"]),
            f"{r['percent']:.1f}%" if r["percent"] is not None else "-",
            r["why"] or "",
            (r["title"] or "")[:44],
        )
        for r in records
    ]
    widths = [max(display_width(str(cell)) for cell in column) for column in zip(header, *rows)]
    for row in (header, *rows):
        print("  ".join(pad(str(cell), width) for cell, width in zip(row, widths)).rstrip())


def emit(records, as_table):
    if as_table:
        print_table(records)
    else:
        for record in records:
            print(json.dumps(record, ensure_ascii=False))


def main(argv=None):
    utf8_pipe(sys.stdout)
    utf8_pipe(sys.stderr)
    parser = argparse.ArgumentParser(description="查询 opencode 子会话的上下文占用")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--session", metavar="ID", help="查询单个会话")
    target.add_argument(
        "--children-of",
        metavar="PARENT_ID",
        nargs="?",
        const="",
        help="列出该会话的全部子会话（省略则用 OPENCODE_SESSION_ID）",
    )
    target.add_argument(
        "--candidates",
        action="store_true",
        help="列出能接手实现的子会话：筛掉只读 agent 与运行中的会话，按上下文升序",
    )
    parser.add_argument("--table", action="store_true", help="人类可读表格，默认逐行 JSON")
    args = parser.parse_args(argv)

    paths = debug_paths()
    path = db_path(paths)
    if not os.path.exists(path):
        print(f"找不到会话库：{path}（why=schema）", file=sys.stderr)
        return 2

    try:
        conn = connect(path)
    except sqlite3.Error as exc:
        print(f"会话库不可用：{exc}（why=schema）", file=sys.stderr)
        return 2

    limits = load_limits(paths)
    columns = "id, parent_id, title, agent, model, time_busy, time_idle, time_updated"

    with contextlib.closing(conn):
        try:
            conn.execute("select 1 from session_v2 limit 1")
        except sqlite3.Error as exc:
            print(f"会话库不可用：{exc}（why=schema）", file=sys.stderr)
            return 2

        if args.session:
            row = conn.execute(
                f"select {columns} from session_v2 where id=?", (args.session,)
            ).fetchone()
            if not row:
                print(f"会话不存在：{args.session}", file=sys.stderr)
                return 1
            emit([session_record(conn, row, limits)], args.table)
            return 0

        parent = args.children_of or os.environ.get("OPENCODE_SESSION_ID", "")
        if not parent:
            print("缺少父会话 id：传 --children-of <id>，或设置 OPENCODE_SESSION_ID", file=sys.stderr)
            return 1
        rows = conn.execute(
            f"select {columns} from session_v2 where parent_id=? order by time_updated desc",
            (parent,),
        ).fetchall()
        if not rows:
            print("（无子会话）", file=sys.stderr)
            return 0
        # 只有 --candidates 需要判定"能不能改文件"，其余模式如实列出全部子会话
        writability = agent_writability() if args.candidates else None
        records = [session_record(conn, row, limits, writability) for row in rows]
        if args.candidates:
            records = [
                r for r in records
                if r["status"] != "running" and r["writable"] is not False
            ]
            # 全被筛掉时给一行提示，免得"没有人"和"都不能用"看起来一样
            if not records:
                print("（无候选）", file=sys.stderr)
                return 0
        # 上下文小的排前面：父 agent 选候选时第一个就是最空的
        records.sort(key=lambda r: (r["context"] is None, r["context"] or 0))
        emit(records, args.table)
        return 0


if __name__ == "__main__":
    sys.exit(main())
