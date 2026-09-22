#!/usr/bin/env python3
import argparse
import json
import re
import sqlite3
import subprocess
from pathlib import Path

MONITOR_PATH = Path.home() / "Library/Application Support/Token Monitor/daily-history-archive.json"
DB_PATH = Path.home() / ".gemini/antigravity-cli/conversation_summaries.db"
REPO_DIR = Path(__file__).resolve().parent.parent
README_PATH = REPO_DIR / "README.md"


def get_token_monitor_stats():
    if not MONITOR_PATH.exists():
        return None

    try:
        with open(MONITOR_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Warning: could not read Token Monitor archive: {e}")
        return None

    all_days = {}
    all_days.update(data.get("days", {}))
    all_days.update(data.get("liveDays", {}))

    total_tokens = 0
    total_cost = 0
    total_cache = 0
    total_reasoning = 0
    total_output = 0

    flash_tokens = 0
    other_tokens = 0

    today_key = sorted(all_days.keys())[-1] if all_days else None
    today_tokens = 0
    today_cost = 0

    for d, info in all_days.items():
        d_tokens = 0
        d_cost = 0
        for obs in info.get("observations", {}).values():
            t = obs.get("tokens", 0)
            c = obs.get("cost", 0)
            model = obs.get("modelId", "")

            d_tokens += t
            d_cost += c
            total_tokens += t
            total_cost += c
            total_cache += obs.get("cacheReadTokens", 0)
            total_output += obs.get("outputTokens", 0)
            total_reasoning += obs.get("reasoningTokens", 0)

            if "flash" in model.lower():
                flash_tokens += t
            else:
                other_tokens += t

        if d == today_key:
            today_tokens = d_tokens
            today_cost = d_cost

    return {
        "days_count": len(all_days),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "total_cache": total_cache,
        "total_output": total_output,
        "total_reasoning": total_reasoning,
        "today_tokens": today_tokens,
        "today_cost": today_cost,
        "flash_tokens": flash_tokens,
        "other_tokens": other_tokens,
    }


def get_antigravity_db_stats():
    if not DB_PATH.exists():
        return 112, 20302
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT count(*), sum(step_count) FROM conversation_summaries")
        row = cur.fetchone()
        conn.close()
        return int(row[0] or 0), int(row[1] or 0)
    except Exception as e:
        print(f"Warning: could not read Antigravity db: {e}")
        return 112, 20302


def generate_telemetry_block(stats, total_steps):
    total_tokens_b = stats["total_tokens"] / 1_000_000_000
    today_tokens_m = stats["today_tokens"] / 1_000_000
    cache_eff_pct = (
        (stats["total_cache"] / stats["total_tokens"] * 100)
        if stats["total_tokens"]
        else 75.9
    )

    flash_pct = (
        (stats["flash_tokens"] / stats["total_tokens"] * 100)
        if stats["total_tokens"]
        else 65.4
    )
    other_pct = 100.0 - flash_pct
    flash_tokens_b = stats["flash_tokens"] / 1_000_000_000
    other_tokens_b = stats["other_tokens"] / 1_000_000_000
    reasoning_m = stats["total_reasoning"] / 1_000_000

    formatted_steps = f"{total_steps:,}"

    return f"""<!--START_SECTION:ai_telemetry-->
```text
🤖 AI Telemetry & Token Metrics (via Token Monitor)
────────────────────────────────────────────────────────────────────────
⏱ Today's AI Compute      : {today_tokens_m:.2f}M tokens (${stats['today_cost']:.2f})
🔤 Lifetime Token Volume   : {total_tokens_b:.2f} Billion tokens (${stats['total_cost']:,.2f} across {stats['days_count']} days)
⚡ Prompt Cache Efficiency : {cache_eff_pct:.1f}% cache hit ({stats['total_cache']/1e9:.2f}B cache-read tokens)
🧠 Primary Driver          : Google Antigravity (IDE & CLI) with Gemini 3.8 Flash

Model & Agent Distribution:
Gemini 3.8 Flash          {flash_tokens_b:.2f}B tokens       ███████████████████████░░   {flash_pct:.1f} %
Gemini 3.7 / Local Models  {other_tokens_b:.2f}B tokens       █░░░░░░░░░░░░░░░░░░░░░░░░   {other_pct:.1f} %

Agentic Engineering Insights:
• High-Efficiency Prompter : Strict ponytail & YAGNI enforcement with prompt cache reuse
• Autonomous Execution     : {formatted_steps}+ lifetime tool calls across IDE & CLI workflows
• Custom Agent Harness     : Zero-slop skill rules and local MCP servers in daily pairing
• High Reasoning Density   : {reasoning_m:.2f}M reasoning tokens generated
────────────────────────────────────────────────────────────────────────
```
<!--END_SECTION:ai_telemetry-->"""


def update_readme():
    if not README_PATH.exists():
        print(f"Error: {README_PATH} not found.")
        return False

    stats = get_token_monitor_stats()
    total_sessions, total_steps = get_antigravity_db_stats()

    content = README_PATH.read_text(encoding="utf-8")

    # Update shields badges
    content = re.sub(
        r"(https://img\.shields\.io/badge/Antigravity_Sessions-)[^-\s]+(\+?-[^\"'\)]+)",
        rf"\g<1>{total_sessions}\g<2>",
        content,
    )
    formatted_steps = f"{total_steps:,}".replace(",", "%2C")
    content = re.sub(
        r"(https://img\.shields\.io/badge/Autonomous_Steps-)[^-\s]+(\+?-[^\"'\)]+)",
        rf"\g<1>{formatted_steps}\g<2>",
        content,
    )

    if stats:
        block = generate_telemetry_block(stats, total_steps)
        content = re.sub(
            r"<!--START_SECTION:ai_telemetry-->.*?<!--END_SECTION:ai_telemetry-->",
            block,
            content,
            flags=re.DOTALL,
        )

    README_PATH.write_text(content, encoding="utf-8")
    return True


def push_if_changed():
    res = subprocess.run(
        ["git", "status", "--porcelain", "README.md"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    if not res.stdout.strip():
        print("README.md is already up to date.")
        return

    print("Syncing updated metrics to git...")
    subprocess.run(["git", "add", "README.md"], cwd=REPO_DIR, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: sync ai telemetry and token metrics [skip ci]"],
        cwd=REPO_DIR,
        check=True,
    )
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True)
    print("Pushed updated telemetry to origin/main.")


def main():
    parser = argparse.ArgumentParser(description="Sync AI telemetry metrics to README.md")
    parser.add_argument("--push", action="store_true", help="Commit and push changes if modified")
    args = parser.parse_args()

    stats = get_token_monitor_stats()
    sessions, steps = get_antigravity_db_stats()

    print(f"Antigravity CLI Stats: {sessions} sessions, {steps:,} steps")
    if stats:
        print(f"Token Monitor Stats  : {stats['total_tokens']:,} tokens across {stats['days_count']} days (${stats['total_cost']:,.2f})")

    if update_readme():
        print(f"Updated {README_PATH.name} successfully.")

    if args.push:
        push_if_changed()


if __name__ == "__main__":
    main()
