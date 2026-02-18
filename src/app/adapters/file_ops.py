"""파일 복사/중복명 처리 등 파일 시스템 작업을 담당한다."""

from __future__ import annotations

import shutil
from pathlib import Path


class FileSystemRepository:
    """입력 파일을 대상 폴더로 안전하게 복사한다."""

    # 동일 파일명이 있으면 suffix를 증가시켜 덮어쓰기를 방지한다.
    def copy_with_suffix(self, src: Path, dst_dir: Path, suffix_start: int) -> Path:
        """중복명 충돌을 피하면서 파일을 복사하고 최종 경로를 반환한다."""
        dst_dir.mkdir(parents=True, exist_ok=True)

        stem = src.stem
        suffix = src.suffix
        candidate = dst_dir / f"{stem}{suffix}"
        index = suffix_start

        while candidate.exists():
            candidate = dst_dir / f"{stem}_{index}{suffix}"
            index += 1

        shutil.copy2(src, candidate)
        return candidate
