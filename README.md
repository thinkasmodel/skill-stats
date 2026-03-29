# skill-stats

[中文文档](README_zh.md)

**Analyze which Claude Code skills are actually being used.**

A CLI tool that parses Claude Code session logs (`.jsonl`) to extract and aggregate skill usage data. Distinguishes between **confirmed uses** (Skill tool invocations) and **explores** (SKILL.md reads).

## Why

Skills are passive Markdown files. This tool extracts usage signals from Claude Code's session logs to answer:

- **Which skills get used most?** (confirmed Skill tool invocations)
- **Which skills get read but never invoked?** (explore-only)
- **Which skills never trigger?** Fix their `description` or remove them
- **Usage trends over time**
- **Per-project breakdown**

## Install

### Standalone binary (recommended)

```bash
# Build
pip install pyinstaller
pyinstaller --onefile --name skill-stats --clean --noconfirm skill_stats.py

# Copy to PATH
cp dist/skill-stats /usr/local/bin/

# Run
skill-stats --top 10
```

### pip install

```bash
# Editable install (development)
pip install -e ".[dev]"

# Run
skill-stats --top 10
# or
python skill_stats.py --top 10
```

## Quick Start

```bash
# Basic report
skill-stats

# Top 5 most used skills
skill-stats --top 5

# Show skills that were never triggered
skill-stats --unused

# Breakdown by project
skill-stats --by-project

# Weekly usage trend
skill-stats --timeline weekly

# Only sessions after a date
skill-stats --since 2025-06-01

# JSON output (for piping / dashboards)
skill-stats --json

# Custom session directory
skill-stats --path /path/to/claude/projects
```

## Requirements

- Python 3.10+ (for building; standalone binary has no dependencies)
- pytest for development (`pip install -e ".[dev]"`)

## How It Works

Two signal types:

| Signal | Column | Source | Meaning |
|--------|--------|--------|---------|
| **Invoked** | `Invoked` | `Skill` tool call (`name="Skill"`, `input.skill="xxx"`) | Skill was triggered via `/command` |
| **Browsed** | `Browsed` | `Read`/`View` of a `SKILL.md` file | SKILL.md was read but skill was not triggered |

Other columns:

| Column | Meaning |
|--------|---------|
| **Sessions** | Number of distinct Claude Code sessions where this skill appeared |
| **Projects** | Number of distinct projects where this skill appeared |

Supported skill paths (6 patterns):
- `/mnt/skills/{scope}/{name}/SKILL.md` (sandbox built-in)
- `~/.claude/skills/{name}/SKILL.md` (user global)
- `{project}/.claude/skills/{name}/SKILL.md` (project-level)
- `~/.agents/skills/{name}/SKILL.md` (agents format)
- `~/.openclaw/skills/{name}/SKILL.md` (openclaw)
- `~/.openclaw/workspace/skills/{name}/SKILL.md` (openclaw workspace)

## Sample Output

```
======================================================================
  Skill Usage Report
======================================================================
  Invoked (via /skill command) : 90
  Browsed (SKILL.md read only) : 286
  Total events                 : 376
  Unique skills                : 85
  Sessions scanned             : 78
======================================================================

  Column guide:
    Invoked  = skill was triggered via Skill tool (/command)
    Browsed  = SKILL.md was read but skill was not triggered
    Sessions = number of distinct sessions where skill appeared
    Projects = number of distinct projects where skill appeared

  Rank  Skill                          Invoked  Browsed  Sessions  Projects
  ────  ───────────────────────────── ─────── ──────── ───────── ─────────
  1     superpowers:brainstorming           18        0        15        11
  2     superpowers:writing-plans           11        0        10         7
  3     document-skills:docx                 6        0         3         3
  4     action-card-v2                       0       49        13         3
  5     process                              0       25         4         3

  Never triggered (3 skills):
    - user/pricing
    - user/grow-sustainably
    - examples/skill-creator
```

## License

MIT
