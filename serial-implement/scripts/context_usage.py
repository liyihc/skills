#!/usr/bin/env python3
"""查询 opencode 子会话的上下文占用（只读，不改动任何会话数据）。

上下文 = 该会话最后一条带 tokens 的 assistant 消息的
         input + cache.read + cache.write + output + reasoning，
即真正占用模型窗口的 token 数；百分比按该会话自己模型的 limit.context 折算。

窗口 limit 依次取自：运行中服务端 `GET /api/model` → sqlite kv 的
`models-dev:v2:catalog` → `~/.cache/opencode/models.json`；每条记录带
`limit_source` 说明命中的是哪一级。

本脚本只报事实（context/limit/percent/limit_source/why），不做「合格阈值」
判定；复用条件写在 SKILL.md 第 4 步。

用法：
    context_usage.py --candidates                    # 机械可接手的候选，上下文升序
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
import time
import unicodedata
from collections import Counter
from pathlib import Path

# 能改文件的工具动作。判定"这个子智能体能不能接手实现"时只看这几项，
# 别的动作（read/grep/shell 之类）与写代码无关。
WRITE_ACTIONS = ("edit", "write", "patch")

# /api/model 要起一个子进程；服务端没起时也最多等这么久。
API_TIMEOUT = 10
# 目录缓存超过这个天数只在 stderr 提示，不影响判定：limits 极少变，
# 过期目录也好过完全没有。
CATALOG_STALE_DAYS = 30

# --candidates 的机械排除项。limit-unknown 不在此列：窗口未知但上下文很小
# 的会话仍可能合格，合格阈值由 SKILL.md 规定。
EXCLUDED_WHY = ("running", "no-tokens", "read-only")


def utf8_pipe(stream):
    """管道输出统一按 UTF-8 编码，避免 Windows 控制台代码页把中文标题写坏。"""
    if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text, width):
    return text + " " * max(0, width - display_width(text))


def run_opencode(*args, timeout=30):
    """跑一次 opencode 子命令并返回 stdout；命令不可用时返回 None。"""
    try:
        proc = subprocess.run(
            ["opencode", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
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


def cache_dir(paths):
    if paths.get("cache"):
        return paths["cache"]
    return os.path.join(
        os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")),
        "opencode",
    )


def models_of(provider):
    """provider 条目下的 models 字典；结构异常时当空处理。"""
    models = provider.get("models") if isinstance(provider, dict) else None
    return models if isinstance(models, dict) else {}


def context_of(model):
    """model 条目里的 limit.context；结构异常时当没有。"""
    if not isinstance(model, dict):
        return None
    limit = model.get("limit")
    return limit.get("context") if isinstance(limit, dict) else None


def limits_from_api_payload(raw):
    """`GET /api/model` 的 stdout -> {(provider, model): context}。"""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    data = payload.get("data") if isinstance(payload, dict) else payload
    limits = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        provider = item.get("providerID")
        model = item.get("modelID") or item.get("id")
        limit_info = item.get("limit")
        context = limit_info.get("context") if isinstance(limit_info, dict) else None
        if provider and model and context:
            limits[(provider, model)] = context
    return limits


def api_limits():
    """运行中服务端是首选：它包含用户自建、models.dev 目录里没有的模型。"""
    return limits_from_api_payload(run_opencode("api", "GET", "/api/model", timeout=API_TIMEOUT))


def limits_from_catalog_value(raw):
    """kv 表的 value -> ({(provider, model): context}, updatedAt_ms)。

    v2 把目录缓存在 sqlite 里：value 是 {"updatedAt":…, "body": "<json 字符串>"}，
    body 还要再 json.loads 一次。
    """
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}, None
    if not isinstance(value, dict):
        return {}, None
    try:
        body = json.loads(value.get("body") or "{}")
    except (TypeError, ValueError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    limits = {}
    for provider_id, provider in body.items():
        for model_id, model in models_of(provider).items():
            context = context_of(model)
            if context:
                limits[(provider_id, model_id)] = context
    updated_at = value.get("updatedAt")
    return limits, updated_at if isinstance(updated_at, int) else None


def catalog_limits(path):
    """从 opencode.db 的 kv 表读 models.dev 目录缓存（离线可用）。"""
    if not path or not os.path.exists(path):
        return {}, None
    try:
        conn = connect(path)
        with contextlib.closing(conn):
            row = conn.execute(
                "select value from kv where key='models-dev:v2:catalog'"
            ).fetchone()
    except sqlite3.Error:
        return {}, None
    if not row:
        return {}, None
    return limits_from_catalog_value(row[0])


def limits_from_models_json(raw):
    """`~/.cache/opencode/models.json` -> {(provider, model): context}。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    limits = {}
    for provider_id, provider in data.items():
        for model_id, model in models_of(provider).items():
            context = context_of(model)
            if context:
                limits[(provider_id, model_id)] = context
    return limits


def file_limits(directory):
    """旧版文件缓存；本机可能不存在，保留为最后回退。"""
    try:
        raw = (Path(directory) / "models.json").read_text(encoding="utf-8")
    except OSError:
        return {}
    return limits_from_models_json(raw)


def gather_sources(paths):
    """按优先级返回 ([(source, limits), …], catalog_updated_at)。"""
    sources = []
    api = api_limits()
    if api:
        sources.append(("api", api))
    catalog, updated_at = catalog_limits(db_path(paths))
    if catalog:
        sources.append(("sqlite", catalog))
    legacy = file_limits(cache_dir(paths))
    if legacy:
        sources.append(("file", legacy))
    return sources, updated_at


def resolve_limit(provider, model, sources):
    """逐 pair 回退：某一级没有这个模型（或没声明 limit）就继续往下找。"""
    if not provider or not model:
        return None, None
    for name, limits in sources:
        limit = limits.get((provider, model))
        if limit:
            return limit, name
    return None, None


def catalog_is_stale(updated_at, now_ms=None):
    if not updated_at:
        return False
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    return now_ms - updated_at > CATALOG_STALE_DAYS * 86_400_000


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


def session_record(conn, row, sources, writability=None):
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
    limit, limit_source = resolve_limit(provider, model, sources)
    percent = round(context * 100 / limit, 1) if (context is not None and limit) else None
    writable = None if writability is None else writability.get(agent)

    # why 只记事实：非空 ≠ 不合格（limit-unknown 仍可能合格），合格线见 SKILL.md
    why = None
    if context is None:
        why = "running" if status == "running" else "no-tokens"
    elif not limit:
        why = "limit-unknown"
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
        "limit_source": limit_source,
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
    header = ("SESSION", "AGENT", "STATUS", "CONTEXT", "PCT", "SRC", "WHY", "TITLE")
    rows = [
        (
            r["session_id"],
            r["agent"] or "-",
            r["status"],
            human_tokens(r["context"]),
            f"{r['percent']:.1f}%" if r["percent"] is not None else "-",
            r["limit_source"] or "-",
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


def report_dropped(records):
    """被机械排除的原因汇总一行，免得"没有人"和"都不可用"看起来一样。"""
    dropped = Counter(r["why"] for r in records if r["why"] in EXCLUDED_WHY)
    if dropped:
        detail = "、".join(f"{why}×{count}" for why, count in dropped.most_common())
        print(f"已排除 {sum(dropped.values())} 个：{detail}", file=sys.stderr)


def warn_stale_catalog(records, updated_at):
    if not catalog_is_stale(updated_at):
        return
    if any(r["limit_source"] == "sqlite" for r in records):
        days = int((time.time() * 1000 - updated_at) / 86_400_000)
        print(
            f"提示：模型目录缓存已 {days} 天未更新（limit 取自 sqlite），结果仍按原值使用",
            file=sys.stderr,
        )


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
        help=(
            "列出机械可接手的子会话：筛掉运行中、无 token 记录与只读 agent，"
            "按上下文升序；合格阈值（percent/绝对 token）见 SKILL.md 第 4 步"
        ),
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
            sources, updated_at = gather_sources(paths)
            record = session_record(conn, row, sources)
            emit([record], args.table)
            warn_stale_catalog([record], updated_at)
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
        sources, updated_at = gather_sources(paths)
        records = [session_record(conn, row, sources, writability) for row in rows]
        if args.candidates:
            kept = [r for r in records if r["why"] not in EXCLUDED_WHY]
            report_dropped(records)
            records = kept
            if not records:
                print("（无候选）", file=sys.stderr)
                return 0
        # 上下文小的排前面：父 agent 选候选时第一个就是最空的
        records.sort(key=lambda r: (r["context"] is None, r["context"] or 0))
        emit(records, args.table)
        warn_stale_catalog(records, updated_at)
        return 0


if __name__ == "__main__":
    sys.exit(main())
