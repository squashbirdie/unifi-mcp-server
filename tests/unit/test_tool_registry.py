"""Unit tests for the read-only mode of src/tool_registry.py.

Read-only mode registers only tools that cannot change state. Tools are classified by
signature (``confirm``/``dry_run``) plus an explicit list, so these tests pin both the
classifier and the invariant that no write-verb tool in the real tool set escapes it.
"""

import importlib
import inspect
import pkgutil
import types
from unittest.mock import MagicMock

import pytest

import src.tools as tools_package
from src.tool_registry import MUTATING_TOOLS_WITHOUT_GATE, is_mutating_tool, register_module_tools

_WRITE_VERBS = (
    "create",
    "update",
    "delete",
    "remove",
    "adopt",
    "restart",
    "upgrade",
    "block",
    "unblock",
    "run",
    "trigger",
    "restore",
    "configure",
    "set",
    "assign",
    "unassign",
    "authorize",
    "unauthorize",
    "limit",
    "reconnect",
    "locate",
    "execute",
    "schedule",
    "toggle",
    "bulk",
    "download",
    "force",
    "start",
    "stop",
    "enable",
    "disable",
    "archive",
    "reboot",
    "reset",
    "clear",
)


def _module_with_tools() -> types.ModuleType:
    module = types.ModuleType("fake_tools")

    async def list_things(site_id: str, settings) -> list:
        return []

    async def update_thing(site_id: str, settings, confirm: bool = False) -> dict:
        return {}

    async def preview_thing(site_id: str, settings, dry_run: bool = False) -> dict:
        return {}

    async def run_speed_test(site_id: str, settings) -> dict:  # no gate, listed explicitly
        return {}

    for fn in (list_things, update_thing, preview_thing, run_speed_test):
        fn.__module__ = module.__name__
        setattr(module, fn.__name__, fn)
    return module


def _settings(read_only: bool) -> MagicMock:
    settings = MagicMock()
    settings.read_only = read_only
    return settings


class TestIsMutatingTool:
    def test_confirm_or_dry_run_marks_a_tool_mutating(self):
        async def a(confirm: bool = False): ...

        async def b(dry_run: bool = False): ...

        assert is_mutating_tool(a)
        assert is_mutating_tool(b)

    def test_plain_read_is_not_mutating(self):
        async def list_things(site_id: str, settings): ...

        assert not is_mutating_tool(list_things)

    def test_listed_tool_without_a_gate_is_mutating(self):
        async def run_speed_test(site_id: str, settings): ...

        assert is_mutating_tool(run_speed_test)

    def test_download_backup_is_treated_as_mutating(self):
        """It changes nothing on the controller but writes a file on the server host."""
        assert "download_backup" in MUTATING_TOOLS_WITHOUT_GATE


class TestRegisterModuleToolsReadOnly:
    def test_read_only_registers_only_non_mutating_tools(self):
        mcp = MagicMock()
        registered = register_module_tools(mcp, _module_with_tools(), _settings(True))

        assert registered == ["list_things"]

    def test_default_registers_every_tool(self):
        mcp = MagicMock()
        registered = register_module_tools(mcp, _module_with_tools(), _settings(False))

        assert sorted(registered) == [
            "list_things",
            "preview_thing",
            "run_speed_test",
            "update_thing",
        ]

    def test_skipped_tools_never_reach_the_server(self):
        mcp = MagicMock()
        register_module_tools(mcp, _module_with_tools(), _settings(True))

        # mcp.tool() is called once per registered tool, so a skipped tool is never exposed
        assert mcp.tool.call_count == 1


def _real_tool_functions():
    for info in pkgutil.iter_modules(tools_package.__path__):
        module = importlib.import_module(f"src.tools.{info.name}")
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if (
                fn.__module__ == module.__name__
                and not name.startswith("_")
                and inspect.iscoroutinefunction(fn)
                and "settings" in inspect.signature(fn).parameters
            ):
                yield module.__name__, name, fn


@pytest.mark.parametrize(
    ("module_name", "name", "fn"),
    [
        pytest.param(m, n, f, id=f"{m.rsplit('.', 1)[-1]}.{n}")
        for m, n, f in _real_tool_functions()
        if n.split("_", 1)[0] in _WRITE_VERBS
    ],
)
def test_every_write_verb_tool_is_hidden_in_read_only_mode(module_name, name, fn):
    """A new tool named like a write must carry confirm/dry_run or be listed, or this fails."""
    assert is_mutating_tool(fn), f"{module_name}.{name} would be exposed by UNIFI_READ_ONLY"


class TestGateFlagCoercion:
    """``dry_run``/``confirm`` arrive as strings from some MCP clients.

    A tool body that tests ``if dry_run:`` treats ``"false"`` as true, so the registry
    wrapper must hand the tool real booleans.
    """

    @staticmethod
    def _wrapped():
        from src.tool_registry import _make_tool_wrapper

        seen: dict = {}

        async def tool(
            site_id: str, settings, confirm: bool | str = False, dry_run: bool | str = False
        ):
            seen.update(confirm=confirm, dry_run=dry_run)
            return seen

        return _make_tool_wrapper(tool, MagicMock()), seen

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("false", False),
            ("False", False),
            ("0", False),
            ("", False),
            ("true", True),
            ("YES", True),
        ],
    )
    async def test_dry_run_string_becomes_bool(self, raw, expected):
        wrapper, seen = self._wrapped()
        await wrapper(site_id="default", confirm="true", dry_run=raw)
        assert seen["dry_run"] is expected
        assert seen["confirm"] is True

    @pytest.mark.asyncio
    async def test_unrecognized_dry_run_string_is_refused_not_read_as_false(self):
        from src.utils.exceptions import ValidationError

        wrapper, seen = self._wrapped()
        with pytest.raises(ValidationError, match="dry_run"):
            await wrapper(site_id="default", confirm=True, dry_run="maybe")
        assert seen == {}

    @pytest.mark.asyncio
    async def test_confirm_string_false_stays_false(self):
        wrapper, seen = self._wrapped()
        await wrapper(site_id="default", confirm="false")
        assert seen["confirm"] is False

    @pytest.mark.asyncio
    async def test_native_booleans_pass_through(self):
        wrapper, seen = self._wrapped()
        await wrapper(site_id="default", confirm=True, dry_run=False)
        assert (seen["confirm"], seen["dry_run"]) == (True, False)
