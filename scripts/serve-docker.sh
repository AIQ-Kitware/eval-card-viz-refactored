#!/usr/bin/env bash
# Build and serve the dashboard with a read-only local results directory.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    cat <<'EOF'
Usage: scripts/serve-docker.sh [RESULTS_DIR] [HOST_IP] [PORT]

Build the Docker image and serve the dashboard at http://localhost:8080.
RESULTS_DIR defaults to the checkout's aiq-evaluations directory when present,
otherwise its bundled evaluations directory. HOST_IP defaults to 127.0.0.1.
PORT defaults to 8080. Use HOST_IP=0.0.0.0 to listen on all IPv4 interfaces.

Environment overrides:
  EVAL_CARD_IMAGE       Image tag (default: eval-card-viz:local)
  EVAL_CARD_CONTAINER   Container name (default: eval-card-viz-local)

The results directory is mounted read-only. Press Ctrl+C to stop the server.
EOF
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi
if (( $# > 3 )); then
    usage >&2
    exit 1
fi

default_results="$repo_dir/aiq-evaluations"
if [[ ! -d "$default_results" ]]; then
    default_results="$repo_dir/evaluations"
fi
results_dir="${1:-$default_results}"
host_ip="${2:-127.0.0.1}"
port="${3:-8080}"
image="${EVAL_CARD_IMAGE:-eval-card-viz:local}"
container="${EVAL_CARD_CONTAINER:-eval-card-viz-local}"

if [[ ! -d "$results_dir" ]]; then
    printf 'Results directory does not exist: %s\n' "$results_dir" >&2
    exit 1
fi
results_dir="$(cd -- "$results_dir" && pwd -P)"
if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
    printf 'Port must be a number from 1 to 65535: %s\n' "$port" >&2
    exit 1
fi
port=$((10#$port))
publish_host="$host_ip"
# Docker's port mapping and browser URLs require brackets around IPv6 addresses.
if [[ "$publish_host" == *:* && "$publish_host" != \[*\] ]]; then
    publish_host="[$publish_host]"
fi
browser_host="$publish_host"
if [[ "$host_ip" == 0.0.0.0 || "$publish_host" == '[::]' ]]; then
    browser_host=localhost
fi
if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker is required. Install Docker and start its daemon first.\n' >&2
    exit 1
fi

docker build --tag "$image" "$repo_dir"
printf '\nBinding to %s:%s\n' "$publish_host" "$port"
printf 'Serving %s at http://%s:%s\n' "$results_dir" "$browser_host" "$port"
printf 'Press Ctrl+C to stop, or run: docker stop %s\n\n' "$container"
exec docker run --rm --init \
    --name "$container" \
    --publish "$publish_host:$port:80" \
    --mount "type=bind,source=$results_dir,target=/deploy/aiq-evaluations,readonly" \
    "$image"
