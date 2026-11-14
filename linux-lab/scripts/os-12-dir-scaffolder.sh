#!/usr/bin/env bash
set -euo pipefail

# OS-12: Directory-Structure Scaffolder (mkdir -p Templates)
# Generates nested directory trees from a template spec with a dry-run preview.

usage() {
  cat <<'EOF'
Usage: os-12-dir-scaffolder.sh [--template <name|file>] [--target <dir>] [--dry-run] [--help]

Options:
  --template <name|file>  Built-in template (web-app, python-pkg, linux-ops) or path to a spec file.
                          Default: web-app
  --target <dir>          Target root directory where the tree will be created.
                          Default: ./scaffold-output
  --dry-run               Preview directories without creating anything on disk.
  --help                  Show this help message and exit.
EOF
}

DRY_RUN=0
TEMPLATE="web-app"
TARGET_DIR="./scaffold-output"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template)
      [[ $# -ge 2 ]] || { echo "Error: --template requires a value." >&2; exit 2; }
      TEMPLATE="$2"
      shift 2
      ;;
    --target)
      [[ $# -ge 2 ]] || { echo "Error: --target requires a value." >&2; exit 2; }
      TARGET_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

get_builtin_spec() {
  case "$1" in
    web-app)
      printf '%s\n' \
        "src/components" \
        "src/pages" \
        "src/assets/images" \
        "src/styles" \
        "tests/unit" \
        "tests/e2e" \
        "docs"
      ;;
    python-pkg)
      printf '%s\n' \
        "src/mypackage/core" \
        "src/mypackage/utils" \
        "tests" \
        "scripts" \
        "docs"
      ;;
    linux-ops)
      printf '%s\n' \
        "configs/nginx" \
        "configs/systemd" \
        "scripts/backup" \
        "scripts/monitoring" \
        "logs/archive"
      ;;
    *)
      return 1
      ;;
  esac
}

SPEC_LINES=()
if [[ -f "$TEMPLATE" ]]; then
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    line="${raw_line%%#*}"
    line="$(printf '%s' "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    SPEC_LINES+=("$line")
  done < "$TEMPLATE"
else
  if ! raw_spec="$(get_builtin_spec "$TEMPLATE")"; then
    echo "Error: Unknown template or missing spec file: $TEMPLATE" >&2
    exit 1
  fi
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    SPEC_LINES+=("$line")
  done <<< "$raw_spec"
fi

if [[ ${#SPEC_LINES[@]} -eq 0 ]]; then
  echo "Error: Template specification is empty." >&2
  exit 1
fi

echo "=== OS-12: Directory-Structure Scaffolder ==="
echo "Template : $TEMPLATE"
echo "Target   : $TARGET_DIR"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Mode     : DRY-RUN (preview only, no directories created)"
else
  echo "Mode     : APPLY (creating nested directories via mkdir -p)"
fi
echo ""

for rel_path in "${SPEC_LINES[@]}"; do
  if [[ "$rel_path" == /* || "$rel_path" == *".."* ]]; then
    echo "Error: Unsafe path in template spec: $rel_path" >&2
    exit 1
  fi
  full_path="${TARGET_DIR%/}/${rel_path}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] mkdir -p \"$full_path\""
  else
    mkdir -p "$full_path"
    echo "[CREATED] $full_path"
  fi
done

echo ""
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Summary: Previewed ${#SPEC_LINES[@]} directories. Re-run without --dry-run to apply."
else
  echo "Summary: Successfully created ${#SPEC_LINES[@]} directories under $TARGET_DIR."
fi
