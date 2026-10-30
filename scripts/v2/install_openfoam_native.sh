#!/usr/bin/env bash
# Native OpenFOAM v2406 (opencfd) for hosts without Docker, e.g. the vast.ai container
# (nvidia/cuda:12.4.1-runtime-ubuntu22.04, running as root). Same version as the Docker image
# opencfd/openfoam-run:2406 used on the laptop, so results are comparable.
# Usage: bash scripts/v2/install_openfoam_native.sh   then   export CFD_BACKEND=native
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

$SUDO apt-get update
$SUDO apt-get install -y --no-install-recommends curl ca-certificates gnupg lsb-release
# opencfd repository (adds /etc/apt/sources.list.d/openfoam.list + key)
curl -fsSL https://dl.openfoam.com/add-debian-repo.sh | $SUDO bash
$SUDO apt-get update
# runtime package (solvers + utilities + OpenMPI + scotch); use openfoam2406-default for tutorials too
$SUDO apt-get install -y --no-install-recommends openfoam2406
# sanity check
bash -c 'source /usr/lib/openfoam/openfoam2406/etc/bashrc && simpleFoam -help >/dev/null && \
  which snappyHexMesh decomposePar mpirun && echo "OpenFOAM $WM_PROJECT_VERSION OK"'
echo "export CFD_BACKEND=native" ; echo "(run as root: the runner sets OMPI_ALLOW_RUN_AS_ROOT=1)"
