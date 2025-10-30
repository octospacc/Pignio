#!/bin/sh
set -e
cd "$(dirname "$(realpath "$0")")"

if [ -e ./README.md ]
then sed -e 's|docs/docs/|docs/|g' ./README.md > ./docs/index.md
fi

if [ -z "$@" ]
then set build
fi

mkdocs $@
