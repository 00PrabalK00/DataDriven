#!/usr/bin/env bash
# One-time setup of a rented vast.ai machine (Ubuntu 22.04 CUDA container, root) for the v2 runs.
# Run ON THE SERVER after the repo subset has been rsynced to /root/DataDriven:
#   bash /root/DataDriven/scripts/v2/server_setup.sh
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq libegl1 libgl1 libglvnd0 libglib2.0-0 libosmesa6 curl rsync htop > /tmp/apt.log 2>&1
command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh > /tmp/uv.log 2>&1)
export PATH=$HOME/.local/bin:$PATH
cd /root/DataDriven/python && uv sync --frozen > /tmp/sync.log 2>&1 && tail -1 /tmp/sync.log
# OpenFOAM (native: Docker is not available inside a vast container)
bash /root/DataDriven/scripts/v2/install_openfoam_native.sh
# rendering smoke test on the GPU (EGL) and the CPU (OSMesa)
cd /root/DataDriven/python
for gl in egl osmesa; do
  MUJOCO_GL=$gl PYOPENGL_PLATFORM=$gl MUJOCO_EGL_DEVICE_ID=0 .venv/bin/python -c "
import mujoco
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><light pos=\"0 0 3\"/><geom size=\"1\"/></worldbody></mujoco>')
r = mujoco.Renderer(m, 64, 64); r.update_scene(mujoco.MjData(m)); print('$gl render ok', r.render().shape)" 2>&1 | grep -v Exception | tail -1
done
nproc; free -g | head -2; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo "SETUP DONE"
