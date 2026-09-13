from __future__ import annotations

import unittest

from server_dashboard.module_api import (
    DashboardOperationError,
    ExtensionRegistry,
    ModuleDescriptor,
    ModuleRegistry,
    OperationSpec,
    no_params,
)


class TypedProviderError(RuntimeError):
    def __init__(self) -> None:
        self.code = "target_not_allowed"
        self.message = "blocked"
        super().__init__(self.message)


class ModuleApiTests(unittest.TestCase):
    def test_disabled_module_blocks_operation(self) -> None:
        registry = ModuleRegistry({})
        registry.register_module(ModuleDescriptor(
            id="example", name="Example", icon="activity", order=1, enabled=False,
        ))
        registry.register_operation(OperationSpec(
            name="ext.example.state", kind="read", module_id="example",
            validator=no_params, handler=lambda cfg, params: {"ok": True},
        ))

        with self.assertRaises(DashboardOperationError) as ctx:
            registry.dispatch("ext.example.state", {})
        self.assertEqual(ctx.exception.code, "module_disabled")

    def test_extension_registry_enforces_ownership(self) -> None:
        registry = ModuleRegistry({})
        scoped = ExtensionRegistry(registry, "example")
        with self.assertRaises(DashboardOperationError) as ctx:
            scoped.register_operation(OperationSpec(
                name="oops.core", kind="read", module_id=None,
                validator=no_params, handler=lambda cfg, params: {},
            ))
        self.assertEqual(ctx.exception.code, "configuration_error")
        self.assertNotIn("oops.core", registry.operations)

    def test_typed_provider_error_preserves_code(self) -> None:
        registry = ModuleRegistry({})
        registry.register_operation(OperationSpec(
            name="test.typed", kind="read", module_id=None,
            validator=no_params,
            handler=lambda cfg, params: (_ for _ in ()).throw(TypedProviderError()),
        ))
        with self.assertRaises(DashboardOperationError) as ctx:
            registry.dispatch("test.typed", {})
        self.assertEqual(ctx.exception.code, "target_not_allowed")
        self.assertEqual(ctx.exception.message, "blocked")


if __name__ == "__main__":
    unittest.main()
