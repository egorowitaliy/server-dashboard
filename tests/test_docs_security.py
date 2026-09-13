from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server_dashboard.docs_provider import DocsProviderError, read_document


class DocsSecurityTests(unittest.TestCase):
    def config(self, root: Path) -> dict:
        return {"docs": {"path": str(root), "extension": ".md", "recursive": True}}

    def test_traversal_external_symlink_and_hidden_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ok.md").write_text("# OK\n", encoding="utf-8")
            (root / "escape.md").symlink_to("/etc/passwd")
            (root / ".hidden.md").write_text("# Hidden\n", encoding="utf-8")
            hidden_dir = root / ".hidden"
            hidden_dir.mkdir()
            (hidden_dir / "nested.md").write_text("# Nested\n", encoding="utf-8")
            config = self.config(root)

            self.assertEqual(read_document(config, "ok.md")["title"], "OK")
            for value in ("../etc/passwd", "escape.md", ".hidden.md", ".hidden/nested.md"):
                with self.subTest(value=value):
                    with self.assertRaises(DocsProviderError):
                        read_document(config, value)

    def test_rendered_markdown_expansion_is_limited(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "large.md").write_text("&" * 300_000, encoding="utf-8")
            with self.assertRaises(DocsProviderError) as ctx:
                read_document(self.config(root), "large.md")
            self.assertEqual(ctx.exception.code, "document_too_large")


if __name__ == "__main__":
    unittest.main()
