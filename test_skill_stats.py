#!/usr/bin/env python3
"""Test skill_stats parsing with synthetic JSONL data covering known formats."""

import json
import os
import sys
import tempfile
import shutil

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))
from skill_stats import extract_skill_calls_from_line, scan_sessions, _extract_skill_name

# ─── Test Data: Known JSONL Formats ─────────────────────────────────────────

# Format 1: session-log hook style (Boucle framework)
HOOK_LOG_LINES = [
    {"ts": "2026-03-15T10:30:00Z", "session": "abc123", "tool": "Read", "detail": "/mnt/skills/public/docx/SKILL.md", "cwd": "/project"},
    {"ts": "2026-03-15T10:31:00Z", "session": "abc123", "tool": "Read", "detail": "/mnt/skills/public/xlsx/SKILL.md", "cwd": "/project"},
    {"ts": "2026-03-15T10:32:00Z", "session": "abc123", "tool": "Read", "detail": "/src/main.py", "cwd": "/project"},  # Not a skill
    {"ts": "2026-03-16T09:00:00Z", "session": "def456", "tool": "Read", "detail": "/mnt/skills/user/validate-idea/SKILL.md", "cwd": "/project2"},
    {"ts": "2026-03-16T09:01:00Z", "session": "def456", "tool": "View", "detail": "/mnt/skills/public/docx/SKILL.md", "cwd": "/project2"},
]

# Format 2: Full assistant message with tool_use content blocks
ASSISTANT_MSG_LINES = [
    {
        "type": "assistant",
        "timestamp": "2026-03-17T14:00:00Z",
        "sessionId": "ghi789",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "Read",
                    "input": {"file_path": "/mnt/skills/public/pptx/SKILL.md"}
                }
            ]
        }
    },
    {
        "type": "assistant",
        "timestamp": "2026-03-17T14:01:00Z",
        "sessionId": "ghi789",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_02",
                    "name": "view",
                    "input": {"path": "/mnt/skills/user/mvp/SKILL.md", "description": "Reading skill"}
                }
            ]
        }
    },
    {
        "type": "assistant",
        "timestamp": "2026-03-17T14:02:00Z",
        "sessionId": "ghi789",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "Let me check the docx skill first."
                },
                {
                    "type": "tool_use",
                    "id": "toolu_03",
                    "name": "Read",
                    "input": {"file_path": "/mnt/skills/public/docx/SKILL.md"}
                }
            ]
        }
    },
]

# Format 3: Direct content array (some variants)
DIRECT_CONTENT_LINES = [
    {
        "timestamp": "2026-03-18T08:00:00Z",
        "sessionId": "jkl012",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_04",
                "name": "Read",
                "input": {"file_path": "/mnt/skills/public/pdf/SKILL.md"}
            }
        ]
    },
]

# Format 4: Non-skill tool calls (should be ignored)
NON_SKILL_LINES = [
    {"ts": "2026-03-15T10:33:00Z", "session": "abc123", "tool": "Bash", "detail": "npm install", "cwd": "/project"},
    {"ts": "2026-03-15T10:34:00Z", "session": "abc123", "tool": "Write", "detail": "/src/app.py", "cwd": "/project"},
    {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/src/main.py"}}
            ]
        }
    },
]


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_skill_name_extraction():
    print("Test: _extract_skill_name")
    
    cases = [
        ("/mnt/skills/public/docx/SKILL.md", "public/docx"),
        ("/mnt/skills/user/validate-idea/SKILL.md", "user/validate-idea"),
        ("/mnt/skills/examples/skill-creator/SKILL.md", "examples/skill-creator"),
        ("/mnt/skills/private/my-skill/SKILL.md", "private/my-skill"),
    ]
    
    for path, expected in cases:
        result = _extract_skill_name(path)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {path} → {result} (expected: {expected})")
    print()


def test_hook_log_format():
    print("Test: Hook log format (session-log style)")
    
    for line in HOOK_LOG_LINES:
        calls = extract_skill_calls_from_line(line)
        detail = line.get("detail", "")
        if "SKILL.md" in detail:
            assert len(calls) == 1, f"Expected 1 call for {detail}, got {len(calls)}"
            print(f"  ✅ {detail} → {calls[0]['skill']}")
        else:
            assert len(calls) == 0, f"Expected 0 calls for {detail}, got {len(calls)}"
            print(f"  ✅ {detail} → (ignored)")
    print()


def test_assistant_message_format():
    print("Test: Assistant message format (tool_use blocks)")
    
    for line in ASSISTANT_MSG_LINES:
        calls = extract_skill_calls_from_line(line)
        assert len(calls) >= 1, f"Expected ≥1 call, got {len(calls)}"
        for c in calls:
            print(f"  ✅ {c['skill_path']} → {c['skill']} (tool: {c['tool']})")
    print()


def test_direct_content_format():
    print("Test: Direct content array format")
    
    for line in DIRECT_CONTENT_LINES:
        calls = extract_skill_calls_from_line(line)
        assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"
        print(f"  ✅ {calls[0]['skill_path']} → {calls[0]['skill']}")
    print()


def test_non_skill_ignored():
    print("Test: Non-skill tool calls are ignored")
    
    for line in NON_SKILL_LINES:
        calls = extract_skill_calls_from_line(line)
        assert len(calls) == 0, f"Expected 0 calls, got {len(calls)}: {calls}"
    print(f"  ✅ All {len(NON_SKILL_LINES)} non-skill lines correctly ignored")
    print()


def test_full_scan():
    print("Test: Full directory scan with mock data")
    
    # Create temp directory structure mimicking ~/.claude/projects/
    tmpdir = tempfile.mkdtemp(prefix="skill-stats-test-")
    try:
        # Project 1
        proj1 = os.path.join(tmpdir, "my-project")
        os.makedirs(proj1)
        with open(os.path.join(proj1, "session-abc123.jsonl"), "w") as f:
            for line in HOOK_LOG_LINES[:3]:
                f.write(json.dumps(line) + "\n")
        
        # Project 2
        proj2 = os.path.join(tmpdir, "other-project")
        os.makedirs(proj2)
        with open(os.path.join(proj2, "session-ghi789.jsonl"), "w") as f:
            for line in ASSISTANT_MSG_LINES:
                f.write(json.dumps(line) + "\n")
            for line in NON_SKILL_LINES:
                f.write(json.dumps(line) + "\n")
        
        # Scan
        calls = scan_sessions(tmpdir)
        
        skills_found = set(c["skill"] for c in calls)
        print(f"  Found {len(calls)} skill calls across {len(skills_found)} unique skills")
        
        for skill in sorted(skills_found):
            count = sum(1 for c in calls if c["skill"] == skill)
            print(f"    · {skill}: {count} calls")
        
        # Verify expected counts
        assert len(calls) >= 5, f"Expected ≥5 calls, got {len(calls)}"
        assert "public/docx" in skills_found, "Should find public/docx"
        assert "public/pptx" in skills_found, "Should find public/pptx"
        assert "user/mvp" in skills_found, "Should find user/mvp"
        
        print(f"  ✅ Full scan passed")
    finally:
        shutil.rmtree(tmpdir)
    print()


def test_report_output():
    """Quick smoke test of report functions (visual check)."""
    from skill_stats import report_summary, report_by_project, report_timeline
    
    print("Test: Report output (visual check)")
    
    tmpdir = tempfile.mkdtemp(prefix="skill-stats-report-")
    try:
        proj1 = os.path.join(tmpdir, "project-alpha")
        os.makedirs(proj1)
        with open(os.path.join(proj1, "session.jsonl"), "w") as f:
            all_lines = HOOK_LOG_LINES + ASSISTANT_MSG_LINES + DIRECT_CONTENT_LINES
            for line in all_lines:
                f.write(json.dumps(line) + "\n")
        
        calls = scan_sessions(tmpdir)
        
        print("\n--- Summary Report ---")
        report_summary(calls, known_skills=["public/docx", "public/xlsx", "public/pptx", "user/mvp", "user/validate-idea", "public/pdf", "user/pricing", "examples/skill-creator"])
        
        print("\n--- By Project ---")
        report_by_project(calls)
        
        print("\n--- Timeline ---")
        report_timeline(calls, "daily")
    finally:
        shutil.rmtree(tmpdir)
    print()


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  skill-stats test suite")
    print("=" * 60)
    print()
    
    test_skill_name_extraction()
    test_hook_log_format()
    test_assistant_message_format()
    test_direct_content_format()
    test_non_skill_ignored()
    test_full_scan()
    test_report_output()
    
    print("=" * 60)
    print("  All tests passed ✅")
    print("=" * 60)
