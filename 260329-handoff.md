# 交接文档 — skill-stats CLI 工具

生成时间：2026-03-29 23:20
工作目录：`/Users/qianli/0-WORKSPACE/15-Skill-SLIM/tools/builtin/skills-usage-stats-cli`
GitHub：https://github.com/thinkasmodel/skill-stats

---

## 1. 当前任务目标

构建一个 CLI 工具 `skill-stats`，从 Claude Code 的 session JSONL 日志中提取 Skill 使用数据，区分「已调用」和「仅浏览」，为 SLIM 平台的 Skill 生态运营提供数据支撑。

**完成标准：**
- v0.1.0 已发布到 GitHub Release，含 Linux/macOS/Windows 三平台二进制
- 后续版本目标：集成到 SLIM 平台作为内置分析引擎

## 2. 当前进展

**已完成（v0.1.0）：**

- 通过 `/office-hours` 产出 design doc（`~/.gstack/projects/skills-usage-stats-cli/qianli--design-20260329-183027.md`）
- 通过 `/plan-eng-review` 完成工程评审，plan 文件在 `~/.claude/plans/sorted-churning-shore.md`
- Outside voice（Claude subagent）发现关键简化：三级信号分层(STRONG/MEDIUM/WEAK)改为二分法(use/explore)，用户已接受
- 核心代码重写完成：`skill_stats.py`（~530 行）
- 测试迁移到 pytest：`test_skill_stats.py`（35 个测试全通过）
- 打包配置：`pyproject.toml`（支持 `pip install -e .` 和 `skill-stats` CLI 入口）
- PyInstaller 打包为独立二进制
- GitHub Actions CI（`.github/workflows/release.yml`）：push tag 自动构建三平台二进制并上传 Release
- v0.1.0 已发布：https://github.com/thinkasmodel/skill-stats/releases/tag/v0.1.0

## 3. 关键上下文

### 用户身份
- SLIM 项目负责人，skill-stats 是 SLIM 的 `tools/builtin/` 下第一个自研工具
- 目标用户：Skill 作者（想知道自己的 skill 有没有人用）和 SLIM 平台运营（需要数据做决策）
- 工具计划同时开源

### 关键决策

1. **二分法信号模型**（非三级分层）：
   - `"use"` = Skill tool 调用（`name="Skill"`, `input.skill="xxx"`）— 权威使用信号
   - `"explore"` = Read/View SKILL.md — 仅浏览
   - 原 design doc 设计了 STRONG/MEDIUM/WEAK 三级 + promote 逻辑，被 outside voice 否定后用户选择简化

2. **6 种 Skill 路径模式**（权威列表在 `skill_stats.py` 的 `SKILL_PATH_PATTERNS`）：
   - `/mnt/skills/{scope}/{name}/SKILL.md` — sandbox
   - `~/.claude/skills/{name}/SKILL.md` — 用户全局
   - `{project}/.claude/skills/{name}/SKILL.md` — 项目级
   - `~/.agents/skills/{name}/SKILL.md`
   - `~/.openclaw/skills/{name}/SKILL.md`
   - `~/.openclaw/workspace/skills/{name}/SKILL.md`

3. **同名 skill 合并**：不同路径下的同名 skill 视为同一个，JSON 输出保留完整路径

4. **零运行时依赖**：纯 Python 标准库，pytest 仅为开发依赖

5. **grep fallback (Strategy 3) 已移除**：outside voice 发现 skill 内容注入到 user message 时会导致大量误报

6. **Strategy 1 (hook log format) 确认为死代码**：真实数据中 0 命中，但代码中保留并标记为 legacy

### 约束
- 用户要求所有响应用中文
- CLAUDE.md 要求 simplicity first、minimal impact
- 自建 Skills 放在 `/Users/qianli/0-WORKSPACE/60-Tools/JChao_Skills/skills`

## 4. 关键发现

1. **Skill tool 调用是权威信号**：真实 JSONL 中格式为 `{"type":"tool_use","name":"Skill","input":{"skill":"superpowers:brainstorming"}}`，共检测到 18 个（样本 200 文件）

2. **Read SKILL.md 不等于使用**：真实数据中 376 个事件，90 个是 Skill tool 调用（use），286 个是 Read（explore）

3. **过滤 user 消息至关重要**：`type:"user"` 的消息中包含被注入的 skill 内容，不过滤会产生大量误报。代码中通过 `if msg_type == "user": return results` 处理

4. **subagent JSONL** 在 `subagents/` 子目录下，`_extract_project_name()` 已处理：归属到父项目

5. **真实数据验证结果**：837 个 session 文件，85 个唯一 skill，78 个 session

## 5. 未完成事项

按优先级排序：

### P1 — 下一版本
1. **用真实 JSONL 数据（脱敏）作为测试用例**（TODOS 中已记录）
   - 现有测试全是合成数据，结构比真实 JSONL 简单
   - 建议从 `~/.claude/projects/` 取几行真实数据脱敏后加入

2. **验证并清理 Strategy 1 (hook log format)**
   - 真实数据中 0 命中，确认是死代码后移除

### P2 — 阶段 2（SLIM 集成）
3. **集成到 SLIM 平台作为内置分析模块**
4. **Web Dashboard**（可视化）
5. **发布到 PyPI**：`pip install skill-stats` / `pipx run skill-stats`

### P3 — Roadmap
6. **Watch mode**：实时监控
7. **Skill description optimizer**：基于误触发模式建议 description 改进
8. **支持 gstack `skill-usage.jsonl` 作为额外数据源**

## 6. 建议接手路径

### 优先查看的文件
1. `skill_stats.py` — 全部核心逻辑（~530 行），重点看 `extract_skill_calls_from_line()` 和 `SKILL_PATH_PATTERNS`
2. `test_skill_stats.py` — 35 个 pytest 测试，理解现有覆盖范围
3. `~/.claude/plans/sorted-churning-shore.md` — eng review plan，包含完整的覆盖率分析和 failure modes
4. `~/.gstack/projects/skills-usage-stats-cli/qianli--design-20260329-183027.md` — design doc（注意：部分内容已被 outside voice 否定，以 plan 文件为准）

### 先验证什么
```bash
cd /Users/qianli/0-WORKSPACE/15-Skill-SLIM/tools/builtin/skills-usage-stats-cli
pytest test_skill_stats.py -v          # 35 tests should pass
python skill_stats.py --top 10         # 真实数据验证
python skill_stats.py --version        # 应输出 0.1.0
./dist/skill-stats --version           # 二进制验证（macOS ARM only）
```

### 推荐下一步
- 如果继续开发：从 P1 的「真实 JSONL 测试数据」开始，这会暴露合成测试遗漏的 edge case
- 如果要发版：改版本号 → `git tag vX.Y.Z && git push origin vX.Y.Z` → CI 自动构建三平台二进制

## 7. 风险与注意事项

1. **Design doc 与实际实现有偏差**：design doc 仍写着三级信号分层和 promote 逻辑，但实际代码采用的是二分法。以 plan 文件和代码为准，不要按 design doc 实现

2. **`macos-13` runner 不可用**：GitHub Actions 中已移除 `macos-13`，只构建 `macos-arm64`。如果需要 macOS x64 二进制，需要找替代方案

3. **pyproject.toml 版本号同步**：`__version__` 在 `skill_stats.py` 中定义，`pyproject.toml` 也有一份。改版本号时两处都要改

4. **不要恢复 grep fallback (Strategy 3)**：outside voice 已验证它会在 skill 内容注入场景下产生大量误报

5. **JSONL 格式可能随 Claude Code 版本变化**：当前检测逻辑基于 2026 年 3 月的 JSONL 格式，如果 Anthropic 改变格式需要适配

---

## 下一位 Agent 的第一步建议

运行 `pytest test_skill_stats.py -v` 确认测试通过，然后运行 `python skill_stats.py --top 10` 看真实输出。读 `skill_stats.py` 的 `extract_skill_calls_from_line()` 函数理解二分法信号检测逻辑。之后根据用户指令决定是继续开发（P1 待办）还是做其他工作。
