"""Tests for DOCX export (D-03)."""

from crypto_trendwatching.application.docx import markdown_to_docx


def test_markdown_to_docx_returns_zip_bytes() -> None:
    markdown = "# Заголовок\n\n## Тренды\n\n- пункт\n\n```json\n{}\n```"
    result = markdown_to_docx(markdown)
    assert isinstance(result, bytes)
    assert result[:2] == b"PK"
    assert len(result) > 0


def test_markdown_to_docx_empty() -> None:
    result = markdown_to_docx("")
    assert isinstance(result, bytes)
    assert result[:2] == b"PK"
