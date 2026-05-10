# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `mode: debono` — De Bono Six Thinking Hats reasoning strategy
- `agents/debono.py` — DebonoOrchestrator for 7-hat sequential pipeline
- `prompts/debono/` — 7 prompt templates (blue_open, white, green, yellow, black, red, blue_close)
- `DEBONO_{HAT}_MODEL` — per-hat model env vars with defaults
- `DEBONO_SKIP_RED` — toggle to skip Red Hat for technical tasks
- `OLLAMA_CLOUD_API_KEY` — cloud API key for hosted models
- `hats/history` — working_document progressive refinement across hats
- Tests — `test_debono_prompts.py`, `test_debono_parsing.py`, `test_debono_flow.py`
- Docs — updated README with debono mode, env vars, architecture

### Changed

- `config.py` — MastMode extended with `debono`, 8 new config fields
- `schemas.py` — HatOutput, DebonoResult, debono field on MastOutput
- `orchestrator.py` — debono branch in run()
- `server.py` — debonoPrimaryModel/debonoCreativeModel params
- `_mast_debate_tool.py` — schema reflects debono overrides
- `prompts/` — reorganized into `debate/` and `debono/` subdirs
- `AGENTS.md` — added De Bono section + coding directives
- `agents/base.py` — cloud auth header injection
- `__main__.py` — cloud-aware doctor (detection, model validation)

## [0.1.0] - 2025-03-27

### Added

- Initial release — drop-in Python replacement for sequential-thinking MCP
- Modes: `passive`, `validate`, `debate`
- Critic agent (mistral:7b-instruct) — identifies reasoning flaws
- Judge agent (deepseek-r1:8b) — synthesizes verdict + suggested revision
- LRU+TLL cache for validation results
- Structured JSON output with Ollama format parameter
- Prompt injection defense via XML data-tags
- Upstream parity — 1:1 port of SequentialThinkingServer from TypeScript
- CI — GitHub Actions with ruff, mypy, pytest
