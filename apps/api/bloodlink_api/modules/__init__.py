"""Domain modules (owner: D1 for the loading order; each module owns its folder).

Importing a module's ``router`` triggers its self-registration with the module
registry, so this list is the single place that defines what the API mounts.
Cross-domain calls still go through each module's ``interfaces.py`` / ``service``
boundary (spec §15, §24).
"""

from __future__ import annotations

MODULE_IMPORTS = (
    "bloodlink_api.modules.auth.router",
    "bloodlink_api.modules.users.router",
    "bloodlink_api.modules.organizations.router",
    "bloodlink_api.modules.admin.router",
    "bloodlink_api.modules.patient_needs.router",
    "bloodlink_api.modules.blood_requests.router",
    "bloodlink_api.modules.donors.router",
    "bloodlink_api.modules.responses.router",
    "bloodlink_api.modules.matching.router",
    "bloodlink_api.modules.notifications.router",
    "bloodlink_api.modules.communication.router",
    "bloodlink_api.modules.donations.router",
)


def load_domain_modules() -> None:
    """Import every domain router so each one self-registers."""
    import importlib

    for module_path in MODULE_IMPORTS:
        importlib.import_module(module_path)
