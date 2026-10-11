#!/usr/bin/env python3
"""Generate the ownership and API-contract docs from the running application.

OWNER: D1 (spec §15, §22, §27).

    python3 scripts/export_contracts.py

Writes:
  * docs/ownership.md      — module -> owner -> folders -> endpoints
  * docs/api-contracts.md  — every endpoint's canonical contract block
  * docs/rbac.md           — capability matrix per role

Because the documents are generated from the same registry and docstrings the API
serves, they cannot silently drift from the code the way hand-written docs do.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for extra in ("apps/api", "packages/config", "packages/contracts", "packages/validation"):
    sys.path.insert(0, str(PROJECT_ROOT / extra))

from bloodlink_api.core.registry import all_modules  # noqa: E402
from bloodlink_api.core.routing import collect_contracts_from_app  # noqa: E402
from bloodlink_api.main import app  # noqa: E402
from bloodlink_contracts.permissions import (  # noqa: E402
    CAPABILITIES_BY_ROLE,
    CAPABILITY_LABELS,
)

OWNED_PATHS: dict[str, list[str]] = {
    "D1": [
        "AGENTS.md",
        "packages/ui/",
        "packages/contracts/",
        "packages/validation/",
        "packages/config/",
        "apps/api/bloodlink_api/core/",
        "apps/api/bloodlink_api/db/",
        "apps/api/bloodlink_api/app.py",
        "apps/api/bloodlink_api/main.py",
        "apps/api/bloodlink_api/seed.py",
        "apps/api/bloodlink_api/modules/auth|users|organizations|admin/",
        "apps/web/src/app/",
        "apps/web/src/api/",
        "apps/web/src/components/",
        "apps/web/src/features/admin/",
        "apps/web/src/features/auth/",
        "alembic/",
        "root configuration",
    ],
    "D2": [
        "apps/api/bloodlink_api/modules/patient_needs/",
        "apps/web/src/features/individual/",
    ],
    "D3": [
        "apps/api/bloodlink_api/modules/blood_requests/",
        "apps/web/src/features/hospital/",
    ],
    "D4": [
        "apps/api/bloodlink_api/modules/matching/",
        "apps/api/bloodlink_api/modules/responses/",
        "apps/api/bloodlink_api/modules/notifications/",
        "apps/api/bloodlink_api/modules/communication/",
        "apps/api/bloodlink_api/modules/donations/",
        "apps/api/bloodlink_api/modules/donors/",
        "apps/web/src/features/donor/",
        "apps/web/src/features/blood-centre/",
    ],
}

OWNER_MISSION = {
    "D1": "Lead / platform foundation — architecture, auth, RBAC, contracts, design system, shells, schema integration, CI rules.",
    "D2": "Individual & PatientNeed — hospital discovery, submission, individual history.",
    "D3": "Hospital & BloodRequest — review gate, request lifecycle, responders, fulfilment.",
    "D4": "Donor & coordination — matching, responses, notifications, threads, donations, subscriptions.",
}

STAMP = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_ownership() -> None:
    lines = [
        "# BloodLink — Ownership Map",
        "",
        f"_Generated from the running application by `scripts/export_contracts.py` on {STAMP}._",
        "",
        "> Feature developers own domain implementation. The Lead owns cross-domain",
        "> architecture and integration (spec §6).",
        "",
        "## Modules",
        "",
        "| Module | Owner | API prefix | Foundation status | Depends on | Scope |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for module in all_modules():
        depends = ", ".join(module.depends_on) or "—"
        lines.append(
            f"| `{module.key}` | **{module.owner}** | `{module.api_prefix}` | {module.foundation_status} | {depends} | {module.description} |"
        )

    lines += ["", "## Owned paths", ""]
    for owner, paths in OWNED_PATHS.items():
        lines.append(f"### {owner} — {OWNER_MISSION[owner]}")
        lines.append("")
        for path in paths:
            lines.append(f"- `{path}`")
        lines.append("")

    lines += [
        "## Shared-file rule",
        "",
        "The following require Lead review (spec §24): shared UI components, design",
        "tokens, API contracts, global types/enums, authentication, authorization,",
        "database architecture, schema/migration integration, root configuration,",
        "package dependencies, application shells and cross-domain interfaces.",
        "",
        "## Feature-folder rule",
        "",
        "Once a module is marked `SCAFFOLD`, the owner replaces the scaffold bodies",
        "with real service calls, flips the status to `IMPLEMENTED`, and removes the",
        "`NotImplemented` marker from the contract docstring. The endpoint paths, DTOs",
        "and error codes do not change without a contract review.",
        "",
    ]
    (PROJECT_ROOT / "docs" / "ownership.md").write_text("\n".join(lines), encoding="utf-8")


def write_contracts() -> None:
    contracts = collect_contracts_from_app(app)
    by_owner: dict[str, list[dict]] = {}
    for contract in contracts:
        by_owner.setdefault(contract["owner"], []).append(contract)

    lines = [
        "# BloodLink — API Contracts",
        "",
        f"_Generated from endpoint docstrings by `scripts/export_contracts.py` on {STAMP}._",
        "",
        f"{len(contracts)} endpoints across {len(all_modules())} modules.",
        "",
        "Every response uses the canonical envelope:",
        "",
        "```json",
        '{ "data": ..., "meta": { "requestId": "...", "generatedAt": "..." }, "error": null }',
        "```",
        "",
        "Every failure uses:",
        "",
        "```json",
        '{ "data": null, "meta": {...}, "error": { "code": "ERROR_CODE", "message": "...", "details": [] } }',
        "```",
        "",
        "## Ownership summary",
        "",
        "| Owner | Endpoints |",
        "| --- | --- |",
    ]
    for owner in ("D1", "D2", "D3", "D4"):
        lines.append(f"| {owner} | {len(by_owner.get(owner, []))} |")
    lines.append("")

    for owner in ("D1", "D2", "D3", "D4"):
        entries = by_owner.get(owner, [])
        if not entries:
            continue
        lines += [f"## {owner} — {OWNER_MISSION[owner]}", ""]
        for contract in entries:
            raw = contract["raw"]
            lines.append(f"### `{contract['method']} {contract['path']}`")
            lines.append("")
            lines.append(f"**Owner:** {owner}  ·  **Status:** {contract['status']}")
            if contract.get("summary"):
                lines.append("")
                lines.append(f"{contract['summary']}")
            lines.append("")
            for key, label in (
                ("AUTHORIZATION", "Authorization"),
                ("INPUT", "Input"),
                ("OUTPUT", "Output"),
                ("STATE CHANGES", "State changes"),
                ("ERRORS", "Errors"),
                ("DEPENDENCIES", "Dependencies"),
                ("MUST NOT", "Must not"),
                ("PRIVACY", "Privacy"),
            ):
                value = raw.get(key)
                if value:
                    lines.append(f"- **{label}:** {value}")
            lines.append("")

    (PROJECT_ROOT / "docs" / "api-contracts.md").write_text("\n".join(lines), encoding="utf-8")


def write_rbac() -> None:
    lines = [
        "# BloodLink — RBAC Capability Matrix",
        "",
        f"_Generated by `scripts/export_contracts.py` on {STAMP}._",
        "",
        "Capabilities are returned to clients by `GET /api/v1/auth/me` so the web",
        "client can build role-aware navigation. The API independently enforces each",
        "rule server-side — frontend guarding is UX only (spec §16).",
        "",
        "| Capability | Description | INDIVIDUAL | HOSPITAL | BLOOD_CENTRE | ADMIN |",
        "| --- | --- | :-: | :-: | :-: | :-: |",
    ]
    all_capabilities = sorted({capability for caps in CAPABILITIES_BY_ROLE.values() for capability in caps})
    for capability in all_capabilities:
        row = [f"`{capability}`", CAPABILITY_LABELS.get(capability, "—")]
        for role in ("INDIVIDUAL", "HOSPITAL", "BLOOD_CENTRE", "ADMIN"):
            from bloodlink_contracts.enums import Role

            row.append("✅" if capability in CAPABILITIES_BY_ROLE[Role(role)] else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    (PROJECT_ROOT / "docs" / "rbac.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    (PROJECT_ROOT / "docs").mkdir(exist_ok=True)
    write_ownership()
    write_contracts()
    write_rbac()
    contracts = collect_contracts_from_app(app)
    print(f"docs/ownership.md, docs/api-contracts.md, docs/rbac.md written ({len(contracts)} endpoints)")


if __name__ == "__main__":
    main()
