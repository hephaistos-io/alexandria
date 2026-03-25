# Alexandria

OSINT platform — Python, data ingestion, ML. See README.md, DESIGN.md, GLOSSARY.md.

## Teaching Project

The developer is learning Python and ML through this project. This changes how you work:

- **Explain the why.** When writing code, briefly explain non-obvious patterns, idioms, or library choices. Not in comments — in your conversation output.
- **Don't hand-wave.** If something is complex (async, decorators, type hints, ORM patterns), explain it when you first introduce it. Assume competence but not Python-specific experience.
- **Introduce concepts incrementally.** Don't dump five new libraries in one step. Build up from simple working code.
- **Flag footguns.** If a pattern is easy to misuse or has a common pitfall, say so.
- **Prefer explicit over clever.** Write readable code over compact code. Avoid magic where possible.
- **When asked to build something, keep the first version simple.** Get it working, then improve. Don't over-engineer on the first pass.
- **Always** append your confidence score to any statements you make. If you would classify your confidence at below 90%, you should take a step back and research the topic thoroughly to improve your confidence in the output
- **Proactively** research topics. You can assume that your knowledge is outdated; your training data cutoff is in the past, so you won't know everything for sure.

## Code Style

- Python 3.13+
- Use `uv` for package management
- `Ruff` for linting/formatting
- Type hints on function signatures
- `src/` layout with `pyproject.toml`
- Tests in `tests/`, mirror the src structure

## Docs

- Keep GLOSSARY.md updated when introducing new terms or acronyms
- DESIGN.md is the technical reference — keep it concise
