# GitHub Release Checklist

This checklist is based on patterns commonly seen in high-visibility skill repositories:

- OpenAI skills: https://github.com/openai/skills
- Anthropic skills: https://github.com/anthropics/skills
- Awesome Claude skills (ComposioHQ): https://github.com/ComposioHQ/awesome-claude-skills
- Awesome Claude skills (VoltAgent): https://github.com/VoltAgent/awesome-claude-skills

Also aligned with GitHub discoverability docs:

- About READMEs: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes
- Repository topics: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics

## Final Verification (Current Repo)

- `SKILL.md` exists with clear scope and execution workflow: PASS
- Local file/script interface is explicit (`input/spec -> outputs`): PASS
- Deterministic scripts exist for rendering/export/mapping: PASS
- LLM-driven color planning interface (`color-plan.json`) exists: PASS
- Multi-round showcase with controllable edits exists: PASS
- PNG/SVG/TikZ outputs are reproducible by scripts: PASS
- Occlusion analysis and quality gate exists: PASS
- README includes quick start + previews + references: PASS
- `.gitignore` present for generated artifacts: PASS
- `LICENSE` file present: PASS
- CI workflow present: PASS

## Upload-Ready Actions

1. Keep `.gitignore` for generated artifacts (`outputs/`, `__pycache__/`, etc.).
2. Keep CI running (Python syntax check + one pipeline smoke run).
3. Keep README first screen focused on:
   - value proposition
   - one command quick start
   - two preview images
4. Configure repository topics in GitHub settings.

## Suggested GitHub Metadata

- Description (EN):
  - `LLM-native conversation chart skill for flowcharts/dataflow/system diagrams with multi-round controllable edits, occlusion-aware rendering, and PNG/SVG/TikZ outputs.`
- Description (ZH):
  - `面向流程图/数据流图/系统架构图的 LLM 对话式绘图 Skill，支持多轮可控编辑、遮蔽检测与 PNG/SVG/TikZ 导出。`
- Suggested topics:
  - `llm`, `ai-agent`, `skill`, `claude-code`, `codex`, `diagram`, `flowchart`, `dataflow`, `tikz`, `svg`, `rag`, `visualization`
