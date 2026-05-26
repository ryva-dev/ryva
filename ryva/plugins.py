from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Callable

from ryva.utils import console

# Global registries
_test_plugins: dict[str, Callable] = {}
_provider_plugins: dict[str, type] = {}


def register_test(name: str, fn: Callable) -> None:
    """Register a custom test type handler."""
    _test_plugins[name] = fn
    console.print(f"[dim]Registered test plugin: {name}[/dim]")


def register_provider(name: str, cls: type) -> None:
    """Register a custom provider."""
    _provider_plugins[name] = cls
    console.print(f"[dim]Registered provider plugin: {name}[/dim]")


def get_test_plugin(name: str) -> Callable | None:
    return _test_plugins.get(name)


def get_provider_plugin(name: str) -> type | None:
    return _provider_plugins.get(name)


def list_plugins() -> dict:
    return {
        "test_types": list(_test_plugins.keys()),
        "providers": list(_provider_plugins.keys()),
    }


def load_plugins() -> None:
    """Auto-discover and load all installed ryva-plugin-* packages."""
    discovered = []

    # Discover via entry points (installed packages)
    try:
        eps = importlib.metadata.entry_points(group="ryva.plugins")
        for ep in eps:
            try:
                ep.load()
                discovered.append(ep.name)
            except Exception as e:
                console.print(f"[yellow]Warning: failed to load plugin '{ep.name}': {e}[/yellow]")
    except Exception:
        pass

    # Discover via installed packages named ryva-plugin-*
    try:
        for dist in importlib.metadata.distributions():
            name = dist.metadata.get("Name", "")
            if name.startswith("ryva-plugin-") and name not in discovered:
                module_name = name.replace("-", "_")
                try:
                    importlib.import_module(module_name)
                    discovered.append(name)
                except ImportError:
                    pass
    except Exception:
        pass

    if discovered:
        console.print(f"[dim]Loaded plugins: {', '.join(discovered)}[/dim]")


def ryva_plugin(name: str, plugin_type: str = "test"):
    """
    Decorator for registering a plugin inline.

    Usage:
        @ryva_plugin("my_test", plugin_type="test")
        def my_test_handler(root, agent_name, input_data, expect, agent_def):
            ...

        @ryva_plugin("my_provider", plugin_type="provider")
        class MyProvider(BaseProvider):
            ...
    """
    def decorator(obj):
        if plugin_type == "test":
            register_test(name, obj)
        elif plugin_type == "provider":
            register_provider(name, obj)
        else:
            console.print(f"[yellow]Unknown plugin type: {plugin_type}[/yellow]")
        return obj
    return decorator
