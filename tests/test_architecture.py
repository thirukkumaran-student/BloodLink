"""Architecture guardrails (D1, spec §3, §22).

The rules that keep a 4-developer monorepo coherent are enforced by tests rather
than by good intentions:

1. The web client never talks to the database — only to the API.
2. The API never depends on the web client.
3. Domain modules do not import each other's internals across ownership lines;
   cross-domain calls go through ``interfaces.py``.
4. No third-party HTTP client library sneaks in (stdlib/httpx only).
5. Shared primitives are defined once (no duplicate global UI or envelope code).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_PKG = PROJECT_ROOT / "apps" / "api" / "bloodlink_api"
WEB_PKG = PROJECT_ROOT / "apps" / "web"
UI_PKG = PROJECT_ROOT / "packages" / "ui"
CONTRACTS = PROJECT_ROOT / "packages" / "contracts" / "bloodlink_contracts"


def _python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_web_client_never_imports_the_database_layer():
    offenders: list[str] = []
    for path in _python_files(WEB_PKG):
        for module in _imports(path):
            if module.startswith("bloodlink_api.db") or module.startswith("sqlalchemy"):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not offenders, f"web client must go through the API: {offenders}"


def test_web_client_never_imports_domain_services():
    """The web app may import contracts/validation, never API services."""
    offenders: list[str] = []
    for path in _python_files(WEB_PKG):
        for module in _imports(path):
            if module.startswith("bloodlink_api.modules") or module.startswith("bloodlink_api.app"):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not offenders, offenders


def test_api_never_imports_the_web_client():
    offenders: list[str] = []
    for path in _python_files(API_PKG):
        for module in _imports(path):
            if module.startswith(("bloodlink_web", "apps.web")):  # the Jinja app is gone; keep the guard for future clients
                offenders.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not offenders, offenders


def test_domain_models_are_declared_once_in_the_canonical_package():
    """Every mapped table class lives under db/models (spec §7, §23)."""
    for path in _python_files(API_PKG / "modules"):
        source = path.read_text(encoding="utf-8")
        assert "class Base" not in source, f"feature module defines its own Base: {path}"
        assert "DeclarativeBase" not in source, f"feature module defines its own Base: {path}"


def test_cross_domain_imports_use_interfaces_or_services_only():
    """A module must not reach into another owner's ``router``/``schemas``."""
    allowed = {"interfaces", "service", "services", "transport"}
    offenders: list[str] = []
    module_root = API_PKG / "modules"
    for path in _python_files(module_root):
        relative = path.relative_to(module_root)
        if len(relative.parts) < 2:
            continue
        owner_module = relative.parts[0]
        for module in _imports(path):
            match = re.match(r"bloodlink_api\.modules\.([a-z_]+)\.([a-z_]+)$", module)
            if not match:
                continue
            other_module, submodule = match.groups()
            if other_module == owner_module or submodule in allowed:
                continue
            offenders.append(f"{relative} -> {module}")
    assert not offenders, f"cross-domain import not via interfaces.py: {offenders}"


def test_no_competing_migration_histories():
    versions = list((PROJECT_ROOT / "alembic" / "versions").glob("*.py"))
    heads_without_parent = []
    for version in versions:
        source = version.read_text(encoding="utf-8")
        if re.search(r"^down_revision = None", source, flags=re.MULTILINE):
            heads_without_parent.append(version.name)
    assert len(heads_without_parent) <= 1, f"multiple migration roots: {heads_without_parent}"


def test_single_response_envelope_implementation():
    sources = [
        path.read_text(encoding="utf-8")
        for path in _python_files(PROJECT_ROOT / "packages" / "contracts")
    ]
    assert any("def success_envelope" in source for source in sources)
    # Nothing outside contracts/envelope.py may hand-build the envelope shape.
    offenders: list[str] = []
    for path in _python_files(API_PKG) + _python_files(WEB_PKG):
        if path.name == "envelope.py" and "core" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if '"data": data, "meta"' in source or "{'data': data, 'meta'" in source:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"duplicate envelope construction: {offenders}"


def test_error_codes_are_declared_in_one_place():
    assert (CONTRACTS / "errors.py").exists()
    offenders: list[str] = []
    for path in _python_files(API_PKG):
        if path.name == "errors.py" and "core" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        if re.search(r"^\s*[A-Z_]+ = \"(UNAUTHENTICATED|FORBIDDEN|NOT_FOUND)\"", source, flags=re.MULTILINE):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"duplicated error-code definitions: {offenders}"


def test_design_system_owns_the_visual_language():
    """Feature screens must not hard-code the global palette (spec §17, §18)."""
    tokens = UI_PKG / "styles" / "tokens.css"
    assert tokens.exists(), "packages/ui/styles/tokens.css must define the design tokens"
    token_source = tokens.read_text(encoding="utf-8")
    for required in ("--bl-color-primary", "--bl-space-", "--bl-radius-", "--bl-font-"):
        assert required in token_source, f"missing token family: {required}"

    # Feature files are allowed to reference tokens, not raw hex values.
    feature_root = WEB_PKG / "src" / "features"
    offenders: list[str] = []
    for path in feature_root.rglob("*"):
        if path.suffix not in {".tsx", ".ts", ".css"}:
            continue
        source = path.read_text(encoding="utf-8")
        if re.search(r"#[0-9a-fA-F]{3,6}\b", source):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert not offenders, f"hard-coded colours in feature code: {offenders}"


def test_no_third_party_http_clients_in_app_code():
    banned = {"requests", "aiohttp", "urllib3", "flask"}
    offenders: list[str] = []
    for root in (API_PKG, WEB_PKG, PROJECT_ROOT / "packages"):
        for path in _python_files(root):
            for module in _imports(path):
                if module.split(".")[0] in banned:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)} -> {module}")
    assert not offenders, offenders


@pytest.mark.parametrize("path", ["AGENTS.md", "docs/ownership.md", "docs/api-contracts.md"])
def test_required_foundation_documents_exist(path: str):
    assert (PROJECT_ROOT / path).exists(), f"{path} is a foundation deliverable (spec §27)"
