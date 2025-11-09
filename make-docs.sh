#!/bin/sh
set -e
cd "$(dirname "$(realpath "$0")")"

if [ -e ./README.md ]
then cat ./README.md | sed -e 's|docs/docs/|docs/|g' | sed -e 's|%20| |g' > ./docs/index.md
fi

if [ -z "$@" ]
then set build
fi

mkdocs $@
