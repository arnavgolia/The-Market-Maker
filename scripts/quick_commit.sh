#!/bin/bash
# Quick commit and push - use this after making changes

cd "$(dirname "$0")/.."

# Run auto-commit script
./scripts/auto_commit.sh
