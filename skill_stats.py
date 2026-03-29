#!/usr/bin/env python3
"""
skill-stats: Analyze Claude Code skill usage from session JSONL logs.

Scans ~/.claude/projects/**/*.jsonl for tool calls that read SKILL.md files,
then aggregates usage by skill name, project, and time.

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
from datetime import datetime, timedelta
from pathlib import Path
import re


# ─── Constants ───────────────────────────────────────────────────────────────

DEFAULT_CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
SKILL_PATH_PATTERN = re.compile(r"(/mnt/skills/[^\"'\s]+/SKILL\.md)")
# Also match Read/View tool calls where the path ends with SKILL.md
SKILL_FILENAME_PATTERN = re.compile(r"SKILL\.md$")


# ─── JSONL Parsing ───────────────────────────────────────────────────────────

def extract_skill_calls_from_line(line_data: dict) -> list[dict]:
    """
    Extract skill-related tool calls from a single JSONL line.
    
    Claude Code JSONL format varies, but tool calls typically appear as:
    - type: "assistant" with content blocks containing tool_use
    - tool name: "Read", "View", "read_file", "view" etc.
    - The input/path field contains the file path
    
    We look for any reference to SKILL.md in tool call paths.
    """
    results = []
    
    # Extract timestamp
    timestamp = line_data.get("timestamp") or line_data.get("ts") or ""
    session_id = line_data.get("sessionId") or line_data.get("session") or ""
    
    # Strategy 1: Direct tool log format (from session-log hook)
    # {"ts":"...","session":"...","tool":"Read","detail":"/mnt/skills/.../SKILL.md"}
    if "tool" in line_data and "detail" in line_data:
        detail = line_data.get("detail", "")
        if SKILL_FILENAME_PATTERN.search(detail):
            skill_name = _extract_skill_name(detail)
            if skill_name:
                results.append({
                    "skill": skill_name,
                    "skill_path": detail,
                    "timestamp": timestamp,
                    "session_id": session_id,
                    "tool": line_data.get("tool", ""),
                })
        return results
    
    # Strategy 2: Full JSONL message format with content blocks
    # {"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"..."}}]}}
    content_sources = []
    
    # Nested message.content
    msg = line_data.get("message", {})
    if isinstance(msg, dict):
        content_sources.append(msg.get("content", []))
    
    # Direct content
    content_sources.append(line_data.get("content", []))
    
    for content in content_sources:
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            
            tool_name = block.get("name", "")
            tool_input = block.get("input", {})
            if not isinstance(tool_input, dict):
                continue
            
            # Check various path field names
            path_value = (
                tool_input.get("file_path")
                or tool_input.get("path")
                or tool_input.get("command")  # bash cat/view commands
                or tool_input.get("description")
                or ""
            )
            
            if SKILL_FILENAME_PATTERN.search(str(path_value)):
                skill_name = _extract_skill_name(str(path_value))
                if skill_name:
                    results.append({
                        "skill": skill_name,
                        "skill_path": str(path_value),
                        "timestamp": timestamp or msg.get("timestamp", ""),
                        "session_id": session_id,
                        "tool": tool_name,
                    })
    
    # Strategy 3: Grep the entire line for SKILL.md paths as fallback
    if not results:
        line_str = json.dumps(line_data)
        matches = SKILL_PATH_PATTERN.findall(line_str)
        for match in matches:
            # Only count if it looks like a tool call context (has "tool_use" or "Read" nearby)
            if any(kw in line_str for kw in ["tool_use", '"Read"', '"View"', '"view"', '"read"', "Read("]):
                skill_name = _extract_skill_name(match)
                if skill_name:
                    results.append({
                        "skill": skill_name,
                        "skill_path": match,
                        "timestamp": timestamp,
                        "session_id": session_id,
                        "tool": "unknown",
                    })
    
    return results


def _extract_skill_name(path: str) -> str | None:
    """Extract skill name from a path like /mnt/skills/public/docx/SKILL.md"""
    # Pattern: /mnt/skills/{scope}/{name}/SKILL.md
    m = re.search(r"/mnt/skills/(\w+)/([^/]+)/SKILL\.md", path)
    if m:
        scope, name = m.group(1), m.group(2)
        return f"{scope}/{name}"
    
    # Fallback: just get the parent directory name
    parts = Path(path).parts
    if len(parts) >= 2:
        return parts[-2]
    
    return None


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
    # Try ISO format as last resort
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
    all_calls = []
    jsonl_files = glob.glob(os.path.join(base_dir, "**", "*.jsonl"), recursive=True)
    
    if not jsonl_files:
        print(f"⚠ No .jsonl files found in {base_dir}", file=sys.stderr)
        return all_calls
    
    print(f"📂 Scanning {len(jsonl_files)} session files...", file=sys.stderr)
    
    for filepath in jsonl_files:
        project_name = _extract_project_name(filepath, base_dir)
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
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
                        
                        # Apply time filter
                        if since:
                            ts = _parse_timestamp(call.get("timestamp", ""))
                            if ts and ts < since:
                                continue
                        
                        all_calls.append(call)
        except (IOError, OSError) as e:
            print(f"⚠ Error reading {filepath}: {e}", file=sys.stderr)
            continue
    
    return all_calls


def _extract_project_name(filepath: str, base_dir: str) -> str:
    """Extract project name from file path."""
    rel = os.path.relpath(filepath, base_dir)
    parts = rel.split(os.sep)
    if len(parts) >= 2:
        return parts[0]
    return "unknown"


# ─── Known Skills Discovery ─────────────────────────────────────────────────

def discover_known_skills(skills_dir: str = "/mnt/skills") -> list[str]:
    """Discover all available skills from the skills directory."""
    skills = []
    if not os.path.exists(skills_dir):
        return skills
    
    for scope in ["public", "user", "private", "examples"]:
        scope_dir = os.path.join(skills_dir, scope)
        if not os.path.isdir(scope_dir):
            continue
        for entry in os.listdir(scope_dir):
            skill_md = os.path.join(scope_dir, entry, "SKILL.md")
            if os.path.isfile(skill_md):
                skills.append(f"{scope}/{entry}")
    
    return sorted(skills)


# ─── Reporting ───────────────────────────────────────────────────────────────

def report_summary(calls: list[dict], top_n: int = 0, known_skills: list[str] | None = None):
    """Print a summary report of skill usage."""
    if not calls:
        print("\n🔍 No skill calls found in session logs.")
        if known_skills:
            print(f"\n📋 {len(known_skills)} skills are installed but none were used in the scanned sessions.")
        return
    
    # Aggregate by skill
    skill_counts = Counter(c["skill"] for c in calls)
    skill_sessions = defaultdict(set)
    skill_projects = defaultdict(set)
    skill_first_seen = {}
    skill_last_seen = {}
    
    for c in calls:
        skill = c["skill"]
        skill_sessions[skill].add(c.get("session_id", ""))
        skill_projects[skill].add(c["project"])
        ts = _parse_timestamp(c.get("timestamp", ""))
        if ts:
            if skill not in skill_first_seen or ts < skill_first_seen[skill]:
                skill_first_seen[skill] = ts
            if skill not in skill_last_seen or ts > skill_last_seen[skill]:
                skill_last_seen[skill] = ts
    
    total_calls = len(calls)
    unique_skills = len(skill_counts)
    unique_sessions = len(set(c.get("session_id", "") for c in calls) - {""})
    
    print(f"\n{'='*60}")
    print(f"  📊 Skill Usage Report")
    print(f"{'='*60}")
    print(f"  Total skill reads : {total_calls}")
    print(f"  Unique skills used: {unique_skills}")
    print(f"  Across sessions   : {unique_sessions}")
    print(f"{'='*60}\n")
    
    # Rankings
    items = skill_counts.most_common(top_n if top_n > 0 else None)
    
    print(f"  {'Rank':<5} {'Skill':<30} {'Calls':>6} {'Sessions':>9} {'Projects':>9}")
    print(f"  {'─'*4}  {'─'*29} {'─'*6} {'─'*9} {'─'*9}")
    
    for i, (skill, count) in enumerate(items, 1):
        sessions = len(skill_sessions[skill] - {""})
        projects = len(skill_projects[skill])
        last = skill_last_seen.get(skill)
        print(f"  {i:<5} {skill:<30} {count:>6} {sessions:>9} {projects:>9}")
    
    # Unused skills
    if known_skills:
        used = set(skill_counts.keys())
        unused = [s for s in known_skills if s not in used]
        if unused:
            print(f"\n  ⚠ Never triggered ({len(unused)} skills):")
            for s in unused:
                print(f"    · {s}")


def report_by_project(calls: list[dict]):
    """Print skill usage broken down by project."""
    project_skills = defaultdict(Counter)
    for c in calls:
        project_skills[c["project"]][c["skill"]] += 1
    
    for project in sorted(project_skills.keys()):
        skills = project_skills[project]
        total = sum(skills.values())
        print(f"\n  📁 {project} ({total} skill calls)")
        for skill, count in skills.most_common():
            bar = "█" * min(count, 30)
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
            # ISO week
            bucket = f"{ts.year}-W{ts.isocalendar()[1]:02d}"
        elif granularity == "monthly":
            bucket = ts.strftime("%Y-%m")
        else:
            bucket = ts.strftime("%Y-%m-%d")
        
        time_buckets[bucket][c["skill"]] += 1
    
    if not time_buckets:
        print("\n  ⚠ No timestamped skill calls found for timeline.")
        return
    
    print(f"\n  📅 Skill Usage Timeline ({granularity})")
    print(f"  {'─'*50}")
    
    for bucket in sorted(time_buckets.keys()):
        skills = time_buckets[bucket]
        total = sum(skills.values())
        top_skill = skills.most_common(1)[0][0] if skills else "?"
        bar = "█" * min(total, 40)
        print(f"  {bucket:<12} {total:>4}  {bar}  ({top_skill})")


def report_json(calls: list[dict], known_skills: list[str] | None = None):
    """Output full report as JSON."""
    skill_counts = Counter(c["skill"] for c in calls)
    skill_sessions = defaultdict(set)
    skill_projects = defaultdict(set)
    
    for c in calls:
        skill_sessions[c["skill"]].add(c.get("session_id", ""))
        skill_projects[c["skill"]].add(c["project"])
    
    report = {
        "summary": {
            "total_calls": len(calls),
            "unique_skills": len(skill_counts),
        },
        "skills": [
            {
                "name": skill,
                "calls": count,
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
        "--path",
        default=DEFAULT_CLAUDE_DIR,
        help=f"Path to Claude projects directory (default: {DEFAULT_CLAUDE_DIR})",
    )
    parser.add_argument(
        "--skills-dir",
        default="/mnt/skills",
        help="Path to skills directory for unused detection (default: /mnt/skills)",
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
            print(f"❌ Invalid date format: {args.since} (expected YYYY-MM-DD)", file=sys.stderr)
            sys.exit(1)
    
    # Discover known skills
    known_skills = None
    if args.unused or args.json_output:
        known_skills = discover_known_skills(args.skills_dir)
    
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
