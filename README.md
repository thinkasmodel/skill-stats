# skill-stats

**Analyze which Claude Code skills are actually being used.**

A CLI tool that parses Claude Code session logs (`.jsonl`) to extract and aggregate skill usage data — showing which `SKILL.md` files were read, how often, across which projects, and over time.

## Why

Skills are passive Markdown files — they can't report their own usage. This tool extracts usage signals from the caller side (Claude Code's session logs) to answer:

- **Which skills get triggered most?** → Prioritize maintenance
- **Which skills never trigger?** → Fix their `description` or remove them
- **Usage trends over time** → Is a skill gaining or losing relevance?
- **Per-project breakdown** → Which workflows depend on which skills?

## Quick Start

```bash
# Basic report (scans ~/.claude/projects/)
python skill_stats.py

# Top 5 most used skills
python skill_stats.py --top 5

# Show skills that were never triggered
python skill_stats.py --unused

# Breakdown by project
python skill_stats.py --by-project

# Weekly usage trend
python skill_stats.py --timeline weekly

# Only sessions after a date
python skill_stats.py --since 2025-06-01

# JSON output (for piping / dashboards)
python skill_stats.py --json

# Custom session directory
python skill_stats.py --path /path/to/claude/projects
```

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

## How It Works

1. Scans `~/.claude/projects/**/*.jsonl` recursively
2. Parses each JSONL line looking for tool calls (`Read`, `View`) where the path matches `*/SKILL.md`
3. Supports multiple JSONL formats:
   - **Hook log format** (e.g. Boucle session-log): `{"tool":"Read","detail":"/mnt/skills/..."}`
   - **Assistant message format**: `{"message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"..."}}]}}`
   - **Direct content format**: `{"content":[{"type":"tool_use",...}]}`
   - **Fallback regex**: Catches any `SKILL.md` path in tool-call context
4. Aggregates by skill name, project, session, and time

## Sample Output

```
============================================================
  📊 Skill Usage Report
============================================================
  Total skill reads : 47
  Unique skills used: 8
  Across sessions   : 23
============================================================

  Rank  Skill                           Calls  Sessions  Projects
  ────  ───────────────────────────── ────── ───────── ─────────
  1     public/docx                        12         8         3
  2     public/xlsx                         9         6         2
  3     user/validate-idea                  7         5         1
  4     public/pptx                         6         4         2
  5     public/pdf                          5         3         2

  ⚠ Never triggered (3 skills):
    · user/pricing
    · user/grow-sustainably
    · examples/skill-creator
```

## Roadmap

- [ ] **Watch mode**: Real-time monitoring as sessions run
- [ ] **Skill description optimizer**: Suggest description improvements based on false-negative patterns
- [ ] **Export to Notion/Obsidian**: Push reports to your knowledge base
- [ ] **Telemetry layer for shared skills**: Webhook-based tracking for skills used by others
- [ ] **npm/pip package**: `npx skill-stats` or `pipx run skill-stats`

## License

MIT
