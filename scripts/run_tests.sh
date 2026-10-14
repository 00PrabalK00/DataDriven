#!/usr/bin/env bash
# Python tests. Plugin autoload is disabled because a system ROS PYTHONPATH injects pytest plugins.
set -euo pipefail
cd "$(dirname "$0")/../python"
export MUJOCO_GL=egl PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
uv run pytest -q "$@"
