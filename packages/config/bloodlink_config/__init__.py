"""bloodlink_config — shared infrastructure configuration (owner: D1).

Keeps logging, environment loading and path resolution in one place so both
applications (``apps/api`` and ``apps/web``) behave identically.
"""

from bloodlink_config.env import load_env_file, read_env  # noqa: F401
from bloodlink_config.logging import configure_logging, get_logger  # noqa: F401
from bloodlink_config.paths import PROJECT_ROOT, WORKSPACE_ROOT, repo_path  # noqa: F401
