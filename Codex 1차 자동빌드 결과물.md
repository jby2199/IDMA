
Implemented the plan end-to-end in code, including core domain logic, adapters, watch service, Tkinter UI, and tests.

What I added

Core domain/types/interfaces: entities.py
Rule engine (ABBR + FULL + AI fallback): rule_engine.py
Phase resolver: phase_resolver.py
Preflight validator: validation.py
File processing use case orchestration: usecases.py
Runtime config model: config_schema.py
Config/knowledge loader + YAML dump: config_loader.py
File copy + duplicate suffix policy: file_ops.py
AI adapter stub: ai_client.py
Excel repository (openpyxl, retry): excel_repo.py
JSONL logger: logger.py
Watch service (watchdog + polling fallback, stabilization, dedupe): file_watcher.py
Tkinter settings UI: settings_window.py
Application bootstrap/entrypoint: main.py
Package exports updated: __init__.py, __init__.py, __init__.py, __init__.py, __init__.py
Tests added

test_rule_engine.py
test_file_ops.py
test_validation.py
test_usecases.py
Verification run

pytest could not be executed because pytest is not installed in the current environment.
Performed compile/smoke checks:
python -m compileall src/app tests succeeded.
Import check import app.main succeeded.
Manual smoke script for classification + usecase copy flow succeeded (smoke-ok).
Notes

PyYAML and openpyxl are handled with lazy import now, so module import is safe even before dependency install.
Runtime execution still requires dependencies when those features are used.
Natural next steps

Install dependencies in .venv: pip install pyyaml openpyxl watchdog pytest
Run tests: PYTHONPATH=src python -m pytest -q
Run app: PYTHONPATH=src python -m app.main


