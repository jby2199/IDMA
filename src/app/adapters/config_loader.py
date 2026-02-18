"""설정 파일(YAML)과 지식 파일(JSON) 로딩/저장을 담당한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.entities import ArtifactEntry, Knowledge
from app.models.config_schema import RuntimeConfig


# 지연 import로 의존성 미설치 환경의 import 실패를 방지한다.
def _load_yaml_module():
    """PyYAML 모듈을 안전하게 로드한다."""
    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required: pip install pyyaml") from exc
    return yaml


# YAML 파일을 dict로 읽어 검증한다.
def load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 읽어 dict 형태로 반환한다."""
    yaml = _load_yaml_module()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


# ledger/app 설정 파일을 합쳐 RuntimeConfig를 생성한다.
def load_runtime_config(ledger_config_path: Path, app_config_path: Path) -> RuntimeConfig:
    """두 YAML 설정 파일을 통합해 RuntimeConfig를 만든다."""
    ledger_data = load_yaml(ledger_config_path)
    app_data = load_yaml(app_config_path)
    return RuntimeConfig.from_dict(ledger_data, app_data)


# RuntimeConfig를 운영 YAML 포맷으로 저장한다.
def dump_runtime_config(path: Path, config: RuntimeConfig) -> None:
    """RuntimeConfig를 ledger.config.yaml 형태로 저장한다."""
    yaml = _load_yaml_module()
    payload = {
        "version": config.version,
        "project_root": str(config.project_root),
        "project_doc_info": {
            "path": config.project_doc_info_path,
            "sheet_name": config.project_doc_info_sheet_name,
            "column_title_doc_no": config.project_doc_info_column_title_doc_no,
            "column_title_abbr": config.project_doc_info_column_title_abbr,
        },
        "workbook": {"path": config.workbook_path},
        "roots": {"source_root": config.source_root, "phase_folders": config.phase_folders},
        "rule": {"full_name_min_ratio": config.full_name_min_ratio},
        "ai": {"confidence_threshold": config.ai_confidence_threshold},
        "fallback": {"enabled": config.fallback_enabled},
        "duplicate": {"suffix_start": config.duplicate_suffix_start},
        "ledgers": {
            "submission": {
                "sheet_name": config.submission_sheet_name,
                "columns": [{"name": name, "ai_attribute": None} for name in config.submission_business_columns],
                "system_columns": list(config.submission_system_columns),
            }
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


# 문서 목록 JSON을 읽어 도메인 Knowledge 모델로 변환한다.
def load_knowledge(path: Path) -> Knowledge:
    """문서 목록 JSON을 파싱해 Knowledge 객체로 반환한다."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    artifacts: list[ArtifactEntry] = []
    phases: list[str] = []
    for phase_node in payload.get("phases", []):
        phase = str(phase_node.get("phase", "")).strip()
        if not phase:
            continue
        phases.append(phase)
        for artifact in phase_node.get("artifacts", []):
            abbr = str(artifact.get("abbr", "")).strip()
            full_name = str(artifact.get("full_name", "")).strip()
            if not abbr or not full_name:
                continue
            artifacts.append(ArtifactEntry(phase=phase, abbr=abbr, full_name=full_name))

    if not phases or not artifacts:
        raise ValueError(f"Knowledge file has no usable phase/artifact rows: {path}")

    return Knowledge(phases=tuple(phases), artifacts=tuple(artifacts))
