from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from server_dashboard.module_api import (
    ModuleDescriptor,
    ModuleRegistry,
    OperationSpec,
    no_params,
)
from server_dashboard.extension_loader import load_extensions


@unittest.skipUnless(os.geteuid() == 0, "ownership checks require root test runner")
class ExtensionLoaderTests(unittest.TestCase):
    def safe_temp_root(self):
        return tempfile.TemporaryDirectory(dir="/root")

    def base_config(self, root: Path, enabled: list[str] | None = None) -> dict:
        return {
            "extensions": {
                "root": str(root),
                "enabled": enabled if enabled is not None else ["example"],
            }
        }

    def prepare_manifest(
        self,
        ext: Path,
        *,
        page: bool = False,
        placements: str = "[]",
        assets: str = "",
        backend: str = '[backend]\nentrypoint = "backend.py"\n',
    ) -> None:
        (ext / "manifest.toml").write_text(
            (
                'api = 1\n'
                'id = "example"\n'
                'name = "Example"\n'
                'version = "1.0.0"\n'
                'icon = "activity"\n'
                f'page = {str(page).lower()}\n'
                f'placements = {placements}\n\n'
                f'{backend}'
                f'{assets}'
            ),
            encoding="utf-8",
        )

    def test_valid_backend_loads(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext)
            (ext / "backend.py").write_text(
                "def register(registry, context):\n    return None\n",
                encoding="utf-8",
            )

            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)

            self.assertEqual(registry.extension_errors, [])
            self.assertIn("example", registry.modules)

    def test_symlink_backend_is_rejected(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext)
            real = root / "real.py"
            real.write_text("def register(registry, context): pass\n", encoding="utf-8")
            (ext / "backend.py").symlink_to(real)

            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)

            self.assertTrue(registry.extension_errors)
            self.assertNotIn("example", registry.modules)

    def test_world_writable_ancestor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as temp:
            root = Path(temp)
            root.chmod(0o755)
            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)
            self.assertTrue(registry.extension_errors)
            self.assertNotIn("example", registry.modules)

    def test_reserved_core_id_cannot_remove_existing_registration(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            cfg = self.base_config(root, ["overview"])
            registry = ModuleRegistry(cfg)
            registry.register_module(ModuleDescriptor(
                id="overview", name="Overview", icon="home", order=1, enabled=True
            ))
            registry.register_operation(OperationSpec(
                name="overview", kind="read", module_id="overview",
                validator=no_params, handler=lambda cfg, params: {"ok": True},
            ))

            load_extensions(registry, cfg)

            self.assertIn("overview", registry.modules)
            self.assertIn("overview", registry.operations)
            self.assertTrue(registry.extension_errors)

    def test_failed_extension_registration_is_transactional(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext)
            (ext / "backend.py").write_text(
                "from server_dashboard.module_api import OperationSpec, no_params\n"
                "def register(registry, context):\n"
                "    registry.register_operation(OperationSpec(\n"
                "        name='ext.example.partial', kind='read', module_id=context.id,\n"
                "        validator=no_params, handler=lambda cfg, params: {}))\n"
                "    raise RuntimeError('boom')\n",
                encoding="utf-8",
            )
            registry = ModuleRegistry(self.base_config(root))
            registry.register_module(ModuleDescriptor(
                id="core", name="Core", icon="home", order=1, enabled=True
            ))

            load_extensions(registry, registry.config)

            self.assertIn("core", registry.modules)
            self.assertNotIn("example", registry.modules)
            self.assertNotIn("ext.example.partial", registry.operations)
            self.assertTrue(registry.extension_errors)

    def test_manifest_assets_must_be_table(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext, assets='assets = "module.js"\n')
            (ext / "backend.py").write_text("def register(registry, context): pass\n")

            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)
            self.assertTrue(registry.extension_errors)
            self.assertNotIn("example", registry.modules)

    def test_page_requires_javascript_asset(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext, page=True)
            (ext / "backend.py").write_text("def register(registry, context): pass\n")

            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)
            self.assertTrue(registry.extension_errors)
            self.assertNotIn("example", registry.modules)

    def test_manifest_backend_must_be_table(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            (ext / "manifest.toml").write_text(
                'api = 1\nid = "example"\nname = "Example"\nversion = "1.0.0"\n'
                'icon = "activity"\npage = false\nplacements = []\nbackend = "backend.py"\n',
                encoding="utf-8",
            )
            registry = ModuleRegistry(self.base_config(root))
            load_extensions(registry, registry.config)
            self.assertTrue(registry.extension_errors)
            self.assertNotIn("example", registry.modules)

    def test_duplicate_enabled_id_does_not_remove_first_extension(self) -> None:
        with self.safe_temp_root() as temp:
            root = Path(temp)
            root.chmod(0o755)
            ext = root / "example"
            ext.mkdir(mode=0o755)
            self.prepare_manifest(ext)
            (ext / "backend.py").write_text(
                "def register(registry, context):\n    return None\n",
                encoding="utf-8",
            )
            cfg = self.base_config(root, ["example", "example"])
            registry = ModuleRegistry(cfg)
            load_extensions(registry, cfg)
            self.assertIn("example", registry.modules)
            self.assertTrue(registry.extension_errors)


if __name__ == "__main__":
    unittest.main()
