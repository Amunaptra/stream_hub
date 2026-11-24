#!/usr/bin/env bash
set -Eeuo pipefail

readonly PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export STREAM_HUB_SOURCE_ROOT="${PACKAGE_ROOT}"

exec "${PACKAGE_ROOT}/hub/installer/install.sh" "$@"
