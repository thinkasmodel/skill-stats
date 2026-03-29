# skill-stats

**分析哪些 Claude Code Skills 真正被使用了。**

一个 CLI 工具，解析 Claude Code 会话日志（`.jsonl`），提取并汇总 Skill 使用数据。区分**已调用**（通过 Skill tool 触发）和**仅浏览**（只读取了 SKILL.md）。

## 为什么需要这个工具

Skills 本质上是被动的 Markdown 文件，你无法直接知道它们是否被用了。这个工具从 Claude Code 的会话日志中提取使用信号，回答以下问题：

- **哪些 Skills 用得最多？**（通过 Skill tool 确认调用的）
- **哪些 Skills 被看了但从没触发？**（仅浏览）
- **哪些 Skills 从没被触发过？** 修改它们的 `description` 或直接删除
- **使用趋势**（按天/周/月）
- **按项目维度的分布**

## 安装

### 独立可执行文件（推荐）

```bash
# 构建
pip install pyinstaller
pyinstaller --onefile --name skill-stats --clean --noconfirm skill_stats.py

# 复制到 PATH
cp dist/skill-stats /usr/local/bin/

# 运行
skill-stats --top 10
```

### pip 安装

```bash
# 开发模式安装
pip install -e ".[dev]"

# 运行
skill-stats --top 10
# 或
python skill_stats.py --top 10
```

## 快速上手

```bash
# 基础报告
skill-stats

# 显示使用量前 5 的 Skills
skill-stats --top 5

# 显示从未被触发的 Skills
skill-stats --unused

# 按项目维度分析
skill-stats --by-project

# 按周显示趋势
skill-stats --timeline weekly

# 只统计某日期之后的会话
skill-stats --since 2025-06-01

# JSON 输出（用于对接 Dashboard 或其他工具）
skill-stats --json

# 指定自定义会话目录
skill-stats --path /path/to/claude/projects
```

## 环境要求

- Python 3.10+（仅构建时需要；独立二进制文件无依赖）
- 开发依赖：pytest（`pip install -e ".[dev]"`）

## 工作原理

### 两种信号类型

| 信号 | 列名 | 数据来源 | 含义 |
|------|------|---------|------|
| **已调用** | `Invoked` | `Skill` tool 调用（`name="Skill"`, `input.skill="xxx"`） | Skill 被通过 `/command` 正式触发 |
| **仅浏览** | `Browsed` | `Read`/`View` 读取了 `SKILL.md` 文件 | SKILL.md 被读取了，但 Skill 未被触发 |

### 其他列说明

| 列名 | 含义 |
|------|------|
| **Sessions** | 该 Skill 出现在多少个不同的 Claude Code 会话中 |
| **Projects** | 该 Skill 出现在多少个不同的项目中 |

### 怎么理解这些数字？

- `Invoked=18, Browsed=0`：这个 Skill 被正式调用了 18 次，每次都是通过 `/command` 触发的，说明它很有用
- `Invoked=0, Browsed=49`：这个 Skill 被读取了 49 次但从未正式触发。可能是 Claude 在探索可用 Skills 时读取了它，也可能是它的 `description` 不够准确导致匹配到了但最终没用
- `Sessions=15, Projects=11`：跨 15 个会话、11 个项目出现过，使用范围广

### 支持的 Skill 路径（6 种）

- `/mnt/skills/{scope}/{name}/SKILL.md`（沙箱内置）
- `~/.claude/skills/{name}/SKILL.md`（用户全局安装）
- `{project}/.claude/skills/{name}/SKILL.md`（项目级安装）
- `~/.agents/skills/{name}/SKILL.md`（agents 格式）
- `~/.openclaw/skills/{name}/SKILL.md`（openclaw 格式）
- `~/.openclaw/workspace/skills/{name}/SKILL.md`（openclaw workspace）

## 输出示例

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

## 许可

MIT
