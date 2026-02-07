"""Tests for ingestion/loaders.py."""

from pathlib import Path

import pytest

from ingestion.loaders import load_documents


class TestLoadDocuments:
    def test_loads_md_and_txt(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# Hello", encoding="utf-8")
        (tmp_path / "b.txt").write_text("World", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 2
        names = {d.name for d in docs}
        assert names == {"a.md", "b.txt"}

    def test_ignores_unsupported_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("ok", encoding="utf-8")
        (tmp_path / "b.py").write_text("print(1)", encoding="utf-8")
        (tmp_path / "c.json").write_text("{}", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert docs[0].name == "a.md"

    def test_limit(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"doc{i}.txt").write_text(f"content {i}", encoding="utf-8")
        docs = load_documents(tmp_path, limit=3)
        assert len(docs) == 3

    def test_recursive(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("deep", encoding="utf-8")
        docs = load_documents(tmp_path)
        assert len(docs) == 1
        assert "sub" in docs[0].path

    def test_empty_dir(self, tmp_path: Path) -> None:
        docs = load_documents(tmp_path)
        assert docs == []

    def test_missing_dir_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_documents("/nonexistent/path/xyz")

    def test_not_a_dir_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            load_documents(f)

    def test_document_content_preserved(self, tmp_path: Path) -> None:
        content = "Some important content\nwith newlines"
        (tmp_path / "doc.txt").write_text(content, encoding="utf-8")
        docs = load_documents(tmp_path)
        assert docs[0].content == content

    def test_document_is_frozen(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        doc = load_documents(tmp_path)[0]
        with pytest.raises(AttributeError):
            doc.content = "changed"  # type: ignore[misc]
