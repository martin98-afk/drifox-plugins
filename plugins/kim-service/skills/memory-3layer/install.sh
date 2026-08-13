#!/usr/bin/env sh
set -eu

platform="auto"
project_dir=""

usage() {
  echo "Usage: ./install.sh --project-dir <path> [--platform auto|claude|codex|both|manual]" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-dir)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      project_dir=$2
      shift 2
      ;;
    --project-dir=*)
      project_dir=${1#*=}
      shift
      ;;
    --platform)
      [ "$#" -ge 2 ] || { usage; exit 2; }
      platform=$2
      shift 2
      ;;
    --platform=*)
      platform=${1#*=}
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

[ -n "$project_dir" ] || { echo "--project-dir is required." >&2; usage; exit 2; }
[ -d "$project_dir" ] || { echo "Project directory does not exist: $project_dir" >&2; exit 2; }

case "$platform" in
  auto|claude|codex|both|manual) ;;
  *) echo "Unsupported platform: $platform" >&2; usage; exit 2 ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
installer="$script_dir/scripts/install_memory_3layer.py"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$installer" --project-dir "$project_dir" --platform "$platform"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$installer" --project-dir "$project_dir" --platform "$platform"
fi

echo "Python 3 was not found on PATH. Install Python 3, then rerun this wrapper." >&2
exit 1
