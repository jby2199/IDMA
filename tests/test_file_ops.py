from pathlib import Path

from app.adapters.file_ops import FileSystemRepository


def test_copy_with_suffix(tmp_path: Path) -> None:
    src = tmp_path / "input.pdf"
    dst_dir = tmp_path / "out"
    src.write_text("v1", encoding="utf-8")

    repo = FileSystemRepository()
    first = repo.copy_with_suffix(src, dst_dir, 1)
    second = repo.copy_with_suffix(src, dst_dir, 1)

    assert first.name == "input.pdf"
    assert second.name == "input_1.pdf"
    assert second.read_text(encoding="utf-8") == "v1"
