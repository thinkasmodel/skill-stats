#!/usr/bin/env python3
"""
skill-stats: Analyze Claude Code skill usage from session JSONL logs.

Scans ~/.claude/projects/**/*.jsonl for skill invocations (Skill tool calls)
and SKILL.md reads, then aggregates usage by skill name, project, and time.

Two signal types:
  - "use"     : Skill tool call (name="Skill", input.skill="xxx") — confirmed usage
  - "explore" : Read/View of a SKILL.md file — browsing, not necessarily used

Usage:
    python skill_stats.py                    # scan default ~/.claude/projects/
    python skill_stats.py --path /custom/dir # scan custom directory
    python skill_stats.py --json             # output as JSON
    python skill_stats.py --top 10           # show top 10 skills
    python skill_stats.py --since 2025-01-01 # filter by date
    python skill_stats.py --unused           # show skills that were never triggered
    python skill_stats.py --by-project       # breakdown by project
    python skill_stats.py --timeline weekly  # show usage over time
"""

import json
import os
import sys
import argparse
import glob
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
import re

__version__ = "0.1.0"

# ─── Constants ───────────────────────────────────────────────────────────────

DEFAULT_CLAUDE_DIR = os.path.expanduser("~/.claude/projects")

# Authoritative path patterns for SKILL.md detection (ordered by priority).
# Each tuple: (compiled_regex, name_extractor_function)
# Priority 1: /mnt/skills/{scope}/{name}/SKILL.md — sandbox built-in
# Priority 2: ~/.claude/skills/{name}/SKILL.md — user global install
# Priority 3: {project}/.claude/skills/{name}/SKILL.md — project install
# Priority 4: ~/.agents/skills/{name}/SKILL.md — agents format
# Priority 5: ~/.openclaw/skills/{name}/SKILL.md — openclaw format
# Priority 6: ~/.openclaw/workspace/skills/{name}/SKILL.md — openclaw workspace
_HOME = re.escape(os.path.expanduser("~"))

SKILL_PATH_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 1. /mnt/skills/{scope}/{name}/SKILL.md
    (re.compile(r"/mnt/skills/(\w+)/([^/]+)/SKILL\.md"), "mnt"),
    # 2. ~/.claude/skills/{name}/SKILL.md (global)
    (re.compile(_HOME + r"/\.claude/skills/([^/]+)/SKILL\.md"), "claude-global"),
    # 3. */.claude/skills/{name}/SKILL.md (project-level, excludes home dir)
    (re.compile(r"(?<!" + _HOME + r")/\.claude/skills/([^/]+)/SKILL\.md"), "claude-project"),
    # 4. ~/.agents/skills/{name}/SKILL.md
    (re.compile(_HOME + r"/\.agents/skills/([^/]+)/SKILL\.md"), "agents"),
    # 5. ~/.openclaw/skills/{name}/SKILL.md
    (re.compile(_HOME + r"/\.openclaw/skills/([^/]+)/SKILL\.md"), "openclaw"),
    # 6. ~/.openclaw/workspace/skills/{name}/SKILL.md
    (re.compile(_HOME + r"/\.openclaw/workspace/skills/([^/]+)/SKILL\.md"), "openclaw-ws"),
]

# Simple check: does a path end with SKILL.md?
SKILL_FILENAME_RE = re.compile(r"SKILL\.md$")


# ─── Skill Name Extraction ──────────────────────────────────────────────────

def _extract_skill_name(path: str) -> str | None:
    """Extract skill name from a SKILL.md path.

    Tries each pattern in priority order. For /mnt/skills/ paths, returns
    "{scope}/{name}". For all other paths, returns the parent directory name.
    """
    for pattern, kind in SKILL_PATH_PATTERNS:
        m = pattern.search(path)
        if m:
            if kind == "mnt":
                return f"{m.group(1)}/{m.group(2)}"
            return m.group(1)

    # Fallback: parent directory of SKILL.md
    parts = Path(path).parts
    if len(parts) >= 2:
        return parts[-2]

    return None


# ─── JSONL Parsing ───────────────────────────────────────────────────────────

def extract_skill_calls_from_line(line_data: dict) -> list[dict]:
    """Extract skill-related events from a single JSONL line.

    Returns a list of dicts with keys:
        skill, skill_path, timestamp, session_id, tool, signal_level
    where signal_level is "use" (Skill tool invocation) or "explore" (Read SKILL.md).
    """
    results = []

    timestamp = line_data.get("timestamp") or line_data.get("ts") or ""
    session_id = line_data.get("sessionId") or line_data.get("session") or ""

    # Only process assistant messages with tool_use blocks.
    # Skip user/tool_result messages to avoid false positives from injected skill content.
    msg_type = line_data.get("type", "")
    if msg_type == "user":
        return results

    # Collect content blocks from nested message.content and direct content
    content_sources = []
    msg = line_data.get("message", {})
    if isinstance(msg, dict):
        content_sources.append(msg.get("content", []))
    content_sources.append(line_data.get("content", []))

    for content in content_sources:
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tool_input = block.get("input", {})
            if not isinstance(tool_input, dict):
                continue

            # Signal: USE — Skill tool invocation
            if tool_name == "Skill":
                skill_value = tool_input.get("skill", "")
                if skill_value:
                    results.append({
                        "skill": skill_value,
                        "skill_path": "",
                        "timestamp": timestamp or msg.get("timestamp", ""),
                        "session_id": session_id,
                        "tool": "Skill",
                        "signal_level": "use",
                    })
                continue

            # Signal: EXPLORE — Read/View of SKILL.md
            path_value = (
                tool_input.get("file_path")
                or tool_input.get("path")
                or ""
            )

            if path_value and SKILL_FILENAME_RE.search(str(path_value)):
                skill_name = _extract_skill_name(str(path_value))
                if skill_name:
                    results.append({
                        "skill": skill_name,
                        "skill_path": str(path_value),
                        "timestamp": timestamp or msg.get("timestamp", ""),
                        "session_id": session_id,
                        "tool": tool_name,
                        "signal_level": "explore",
                    })

    # Legacy: hook log format ({"tool":"Read","detail":"..."})
    # Kept for backward compat; produces "explore" signal.
    if not results and "tool" in line_data and "detail" in line_data:
        detail = str(line_data.get("detail", ""))
        if SKILL_FILENAME_RE.search(detail):
            skill_name = _extract_skill_name(detail)
            if skill_name:
                results.append({
                    "skill": skill_name,
                    "skill_path": detail,
                    "timestamp": timestamp,
                    "session_id": session_id,
                    "tool": line_data.get("tool", ""),
                    "signal_level": "explore",
                })

    return results


def _parse_timestamp(ts: str) -> datetime | None:
    """Try to parse various timestamp formats."""
    if not ts:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


# ─── Scanning ────────────────────────────────────────────────────────────────

def scan_sessions(
    base_dir: str,
    since: datetime | None = None,
) -> list[dict]:
    """Scan all .jsonl files under base_dir and extract skill calls."""
    all_calls: list[dict] = []
    jsonl_files = glob.glob(os.path.join(base_dir, "**", "*.jsonl"), recursive=True)

    if not jsonl_files:
        print(f"No .jsonl files found in {base_dir}", file=sys.stderr)
        return all_calls

    print(f"Scanning {len(jsonl_files)} session files...", file=sys.stderr)

    for filepath in jsonl_files:
        project_name = _extract_project_name(filepath, base_dir)

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    calls = extract_skill_calls_from_line(data)
                    for call in calls:
                        call["project"] = project_name
                        call["source_file"] = filepath

                        if since:
                            ts = _parse_timestamp(call.get("timestamp", ""))
                            if ts and ts < since:
                                continue

                        all_calls.append(call)
        except (IOError, OSError) as e:
            print(f"Error reading {filepath}: {e}", file=sys.stderr)
            continue

    return all_calls


def _extract_project_name(filepath: str, base_dir: str) -> str:
    """Extract project name from file path.

    Handles subagent paths: if the JSONL is under a subagents/ directory,
    attribute it to the parent project rather than treating "subagents" as
    the project name.
    """
    rel = os.path.relpath(filepath, base_dir)
    parts = rel.split(os.sep)
    if len(parts) >= 2:
        # Skip "subagents" directory level
        if len(parts) >= 3 and parts[1] == "subagents":
            return parts[0]
        return parts[0]
    return "unknown"


# ─── Known Skills Discovery ─────────────────────────────────────────────────

DEFAULT_SKILL_DIRS = [
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.agents/skills"),
    os.path.expanduser("~/.openclaw/skills"),
    os.path.expanduser("~/.openclaw/workspace/skills"),
    "/mnt/skills",
]


def discover_known_skills(extra_dirs: list[str] | None = None) -> list[str]:
    """Discover all installed skills across all known directories.

    Scans:
    - ~/.claude/skills/{name}/SKILL.md
    - ~/.agents/skills/{name}/SKILL.md
    - ~/.openclaw/skills/{name}/SKILL.md
    - ~/.openclaw/workspace/skills/{name}/SKILL.md
    - /mnt/skills/{scope}/{name}/SKILL.md
    - Project-level .claude/skills/ (if extra_dirs provided)
    """
    skills: set[str] = set()

    dirs_to_scan = list(DEFAULT_SKILL_DIRS)
    if extra_dirs:
        dirs_to_scan.extend(extra_dirs)

    for base in dirs_to_scan:
        if not os.path.isdir(base):
            continue

        if base == "/mnt/skills":
            # /mnt/skills has scope subdirectories
            for scope in os.listdir(base):
                scope_dir = os.path.join(base, scope)
                if not os.path.isdir(scope_dir):
                    continue
                for entry in os.listdir(scope_dir):
                    if os.path.isfile(os.path.join(scope_dir, entry, "SKILL.md")):
                        skills.add(f"{scope}/{entry}")
        else:
            # Flat structure: {base}/{name}/SKILL.md
            for entry in os.listdir(base):
                if os.path.isfile(os.path.join(base, entry, "SKILL.md")):
                    skills.add(entry)

    return sorted(skills)


# ─── Reporting ───────────────────────────────────────────────────────────────

def report_summary(calls: list[dict], top_n: int = 0, known_skills: list[str] | None = None):
    """Print a summary report of skill usage."""
    if not calls:
        print("\nNo skill calls found in session logs.")
        if known_skills:
            print(f"\n{len(known_skills)} skills are installed but none were used in the scanned sessions.")
        return

    uses = [c for c in calls if c.get("signal_level") == "use"]
    explores = [c for c in calls if c.get("signal_level") == "explore"]

    # Aggregate by skill
    skill_counts = Counter(c["skill"] for c in calls)
    use_counts = Counter(c["skill"] for c in uses)
    explore_counts = Counter(c["skill"] for c in explores)
    skill_sessions = defaultdict(set)
    skill_projects = defaultdict(set)

    for c in calls:
        skill = c["skill"]
        skill_sessions[skill].add(c.get("session_id", ""))
        skill_projects[skill].add(c["project"])

    total_calls = len(calls)
    unique_skills = len(skill_counts)
    unique_sessions = len(set(c.get("session_id", "") for c in calls) - {""})

    print(f"\n{'='*70}")
    print(f"  Skill Usage Report")
    print(f"{'='*70}")
    print(f"  Invoked (via /skill command) : {len(uses)}")
    print(f"  Browsed (SKILL.md read only) : {len(explores)}")
    print(f"  Total events                 : {total_calls}")
    print(f"  Unique skills                : {unique_skills}")
    print(f"  Sessions scanned             : {unique_sessions}")
    print(f"{'='*70}")
    print()
    print(f"  Column guide:")
    print(f"    Invoked  = skill was triggered via Skill tool (/command)")
    print(f"    Browsed  = SKILL.md was read but skill was not triggered")
    print(f"    Sessions = number of distinct sessions where skill appeared")
    print(f"    Projects = number of distinct projects where skill appeared")
    print()

    # Rankings
    items = skill_counts.most_common(top_n if top_n > 0 else None)

    print(f"  {'Rank':<5} {'Skill':<30} {'Invoked':>7} {'Browsed':>8} {'Sessions':>9} {'Projects':>9}")
    print(f"  {'─'*4}  {'─'*29} {'─'*7} {'─'*8} {'─'*9} {'─'*9}")

    for i, (skill, _) in enumerate(items, 1):
        u = use_counts.get(skill, 0)
        e = explore_counts.get(skill, 0)
        sessions = len(skill_sessions[skill] - {""})
        projects = len(skill_projects[skill])
        print(f"  {i:<5} {skill:<30} {u:>7} {e:>8} {sessions:>9} {projects:>9}")

    # Unused skills
    if known_skills:
        used = set(skill_counts.keys())
        unused = [s for s in known_skills if s not in used]
        if unused:
            print(f"\n  Never triggered ({len(unused)} skills):")
            for s in unused:
                print(f"    - {s}")


def report_by_project(calls: list[dict]):
    """Print skill usage broken down by project."""
    project_skills = defaultdict(Counter)
    for c in calls:
        project_skills[c["project"]][c["skill"]] += 1

    for project in sorted(project_skills.keys()):
        skills = project_skills[project]
        total = sum(skills.values())
        print(f"\n  {project} ({total} skill events)")
        for skill, count in skills.most_common():
            bar = "=" * min(count, 30)
            print(f"     {skill:<30} {count:>4}  {bar}")


def report_timeline(calls: list[dict], granularity: str = "weekly"):
    """Print skill usage over time."""
    time_buckets = defaultdict(Counter)

    for c in calls:
        ts = _parse_timestamp(c.get("timestamp", ""))
        if not ts:
            continue

        if granularity == "daily":
            bucket = ts.strftime("%Y-%m-%d")
        elif granularity == "weekly":
            bucket = f"{ts.year}-W{ts.isocalendar()[1]:02d}"
        elif granularity == "monthly":
            bucket = ts.strftime("%Y-%m")
        else:
            bucket = ts.strftime("%Y-%m-%d")

        time_buckets[bucket][c["skill"]] += 1

    if not time_buckets:
        print("\n  No timestamped skill calls found for timeline.")
        return

    print(f"\n  Skill Usage Timeline ({granularity})")
    print(f"  {'─'*50}")

    for bucket in sorted(time_buckets.keys()):
        skills = time_buckets[bucket]
        total = sum(skills.values())
        top_skill = skills.most_common(1)[0][0] if skills else "?"
        bar = "=" * min(total, 40)
        print(f"  {bucket:<12} {total:>4}  {bar}  ({top_skill})")


def report_json(calls: list[dict], known_skills: list[str] | None = None):
    """Output full report as JSON."""
    uses = [c for c in calls if c.get("signal_level") == "use"]
    explores = [c for c in calls if c.get("signal_level") == "explore"]

    skill_counts = Counter(c["skill"] for c in calls)
    use_counts = Counter(c["skill"] for c in uses)
    explore_counts = Counter(c["skill"] for c in explores)
    skill_sessions = defaultdict(set)
    skill_projects = defaultdict(set)

    for c in calls:
        skill_sessions[c["skill"]].add(c.get("session_id", ""))
        skill_projects[c["skill"]].add(c["project"])

    report = {
        "summary": {
            "total_events": len(calls),
            "confirmed_uses": len(uses),
            "explores": len(explores),
            "unique_skills": len(skill_counts),
        },
        "skills": [
            {
                "name": skill,
                "uses": use_counts.get(skill, 0),
                "explores": explore_counts.get(skill, 0),
                "total": count,
                "sessions": len(skill_sessions[skill] - {""}),
                "projects": sorted(skill_projects[skill]),
            }
            for skill, count in skill_counts.most_common()
        ],
    }

    if known_skills:
        used = set(skill_counts.keys())
        report["unused_skills"] = [s for s in known_skills if s not in used]

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="skill-stats",
        description="Analyze Claude Code skill usage from session JSONL logs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # basic usage report
  %(prog)s --top 5                  # top 5 most used skills
  %(prog)s --unused                 # show never-triggered skills
  %(prog)s --by-project             # breakdown by project
  %(prog)s --timeline weekly        # usage trend over weeks
  %(prog)s --since 2025-06-01       # only sessions after June 2025
  %(prog)s --json                   # machine-readable output
  %(prog)s --path ~/my-claude-dir   # custom session directory
        """,
    )

    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--path",
        default=DEFAULT_CLAUDE_DIR,
        help=f"Path to Claude projects directory (default: {DEFAULT_CLAUDE_DIR})",
    )
    parser.add_argument(
        "--top", type=int, default=0,
        help="Show only top N skills (default: show all)",
    )
    parser.add_argument(
        "--since",
        help="Only count calls after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--unused", action="store_true",
        help="Show skills that were never triggered",
    )
    parser.add_argument(
        "--by-project", action="store_true",
        help="Show skill usage broken down by project",
    )
    parser.add_argument(
        "--timeline",
        choices=["daily", "weekly", "monthly"],
        help="Show skill usage over time",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )

    args = parser.parse_args()

    # Parse --since
    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d")
        except ValueError:
            print(f"Invalid date format: {args.since} (expected YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)

    # Discover known skills
    known_skills = None
    if args.unused or args.json_output:
        known_skills = discover_known_skills()

    # Scan
    calls = scan_sessions(args.path, since=since)

    # Report
    if args.json_output:
        report_json(calls, known_skills)
    elif args.by_project:
        report_by_project(calls)
    elif args.timeline:
        report_timeline(calls, args.timeline)
    else:
        report_summary(calls, top_n=args.top, known_skills=known_skills if args.unused else None)


if __name__ == "__main__":
    main()
