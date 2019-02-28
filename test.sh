#!/bin/bash
set -e

usage() { echo "* Usage: $0 [app_or_apps_to_test][--fast][--with-migrations][--skip-linter][--skip-coverage]" >&2; exit 1; }

LINTER=true
COVERAGE=true
POSITIONAL=()

# Parse arguments.
for PARAM in $@; do
    case $PARAM in
        --fast)
          LINTER=false
          COVERAGE=false
        ;;
        --with-migrations)
          export TEST_MIGRATIONS=true
          ;;
        --skip-linter)
          LINTER=false
          ;;
        --skip-coverage)
          COVERAGE=false
          ;;
        --help)
          usage
          ;;
        *)
          POSITIONAL+=($PARAM)
          ;;
    esac
done

set -- "${POSITIONAL[@]}" # restore positional parameters

if $LINTER; then
    make lint
fi

CMD="manage.py test --noinput --parallel ${PARALLEL_COUNT:-2} $*"

if [ "${LEGACY_CODEBOX_ENABLED:-false}" != "true" ]; then
    CMD="${CMD} --exclude-tag legacy_codebox"
fi

# Run tests
export DJANGO_SETTINGS_MODULE=settings.tests
if $COVERAGE; then
    coverage erase
    coverage run $CMD
    coverage combine
else
    python $CMD
fi

if $COVERAGE; then
    echo
    echo "=== coverage report ==="
    coverage report
fi
