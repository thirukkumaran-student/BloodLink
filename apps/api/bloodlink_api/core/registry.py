"""Module registry (owner: D1, spec §22).

One place lists every domain module, its owner and its prefix. The app factory
mounts them; ``/api/v1/platform/modules`` and the generated ownership docs read
the same list. Adding a domain therefore requires exactly one edit — here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    owner: str
    domain: str
    api_prefix: str
    description: str
    foundation_status: str = "SCAFFOLD"
    router: APIRouter | None = None
    #: Additional top-level routers the module mounts under `/api/v1`
    #: (e.g. D4 serves donors at `/donor` and blood centres at `/blood-centres`).
    extra_routers: tuple[APIRouter, ...] = field(default_factory=tuple)
    depends_on: tuple[str, ...] = field(default_factory=tuple)


_MODULES: list[ModuleSpec] = []


def register_module(spec: ModuleSpec) -> ModuleSpec:
    if any(existing.key == spec.key for existing in _MODULES):
        raise ValueError(f"Module '{spec.key}' is already registered")
    _MODULES.append(spec)
    return spec


def all_modules() -> list[ModuleSpec]:
    _load_modules()
    return list(_MODULES)


def routers() -> list[APIRouter]:
    collected: list[APIRouter] = []
    for module in all_modules():
        if module.router is not None:
            collected.append(module.router)
        collected.extend(module.extra_routers)
    return collected


def module_summary() -> list[dict]:
    return [
        {
            "key": module.key,
            "owner": module.owner,
            "domain": module.domain,
            "prefix": module.api_prefix,
            "description": module.description,
            "status": module.foundation_status,
            "dependsOn": list(module.depends_on),
        }
        for module in all_modules()
    ]


_loaded = False


def _load_modules() -> None:
    """Import every domain module so each self-registers (avoids import cycles)."""
    global _loaded
    if _loaded:
        return
    from bloodlink_api.modules import load_domain_modules

    load_domain_modules()
    _loaded = True
