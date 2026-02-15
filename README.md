# Python Project Template

This folder is a reusable Python project template containing a minimal, opinionated structure:

- `src/app/` — application package (core, adapters, models, utils)
- `tests/` — example pytest tests
- `pyproject.toml`, `README.md`, `.gitignore`

Run tests:

```bash
python -m pip install pytest
python -m pytest -q
```

Customize as needed for your project.


---
# 프로젝트 폴더 구조 설명
- 판단/계산은 core
- 파일/엑셀/외부접촉은 adapters
- 데이터 모양은 models
- 애매하면 utils

---
# 세팅
## VS Code에서 흔히 하는 실수 2개 (미리 방지)
✅ 실수 1: 인터프리터를 .venv로 안 맞춤
- Ctrl+Shift+P
- “Python: Select Interpreter”
- .venv 선택