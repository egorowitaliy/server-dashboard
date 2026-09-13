from server_dashboard.module_api import OperationSpec, no_params


def register(registry, context):
    registry.register_operation(
        OperationSpec(
            name="ext.example-status.state",
            kind="read",
            module_id=context.id,
            validator=no_params,
            handler=lambda dashboard_config, params: {
                "status": "ok",
                "value": "Работает",
            },
        )
    )
