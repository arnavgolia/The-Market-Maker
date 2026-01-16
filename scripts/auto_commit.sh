#!/bin/bash
# Auto-commit and push script for The Market Maker
# This script commits and pushes changes automatically

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔄 Auto-commit script starting...${NC}"

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo -e "${RED}❌ Not a git repository. Initializing...${NC}"
    git init
    echo -e "${GREEN}✅ Git repository initialized${NC}"
fi

# Check if there's a remote
if ! git remote | grep -q origin; then
    echo -e "${YELLOW}⚠️  No remote 'origin' found.${NC}"
    echo "Please add a remote with: git remote add origin <your-repo-url>"
    exit 1
fi

# Get current branch
BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Check for changes
if git diff --quiet && git diff --cached --quiet; then
    echo -e "${YELLOW}ℹ️  No changes to commit${NC}"
    exit 0
fi

# Get list of changed files
CHANGED_FILES=$(git diff --name-only HEAD)
STAGED_FILES=$(git diff --cached --name-only)

# Determine commit message based on changes
if echo "$CHANGED_FILES $STAGED_FILES" | grep -q "dashboard"; then
    COMMIT_MSG="✨ Update dashboard UI and features"
elif echo "$CHANGED_FILES $STAGED_FILES" | grep -q "simulation\|SIMULATION"; then
    COMMIT_MSG="🎮 Add simulation mode (no API required)"
elif echo "$CHANGED_FILES $STAGED_FILES" | grep -q "test"; then
    COMMIT_MSG="🧪 Update tests"
elif echo "$CHANGED_FILES $STAGED_FILES" | grep -q "config"; then
    COMMIT_MSG="⚙️  Update configuration"
elif echo "$CHANGED_FILES $STAGED_FILES" | grep -q "\.py$"; then
    COMMIT_MSG="🔧 Update core functionality"
elif echo "$CHANGED_FILES $STAGED_FILES" | grep -q "README\|\.md"; then
    COMMIT_MSG="📝 Update documentation"
else
    COMMIT_MSG="🔄 Auto-commit: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Add all changes (respecting .gitignore)
echo -e "${GREEN}📦 Staging changes...${NC}"
git add -A

# Show what's being committed
echo -e "${GREEN}📋 Changes to commit:${NC}"
git status --short

# Commit
echo -e "${GREEN}💾 Committing changes...${NC}"
git commit -m "$COMMIT_MSG" || {
    echo -e "${RED}❌ Commit failed (maybe no changes?)${NC}"
    exit 1
}

# Push
echo -e "${GREEN}🚀 Pushing to origin/$BRANCH...${NC}"
if git push origin "$BRANCH" 2>&1; then
    echo -e "${GREEN}✅ Successfully pushed to GitHub!${NC}"
    echo -e "${GREEN}   Commit: $COMMIT_MSG${NC}"
else
    echo -e "${RED}❌ Push failed. You may need to:${NC}"
    echo -e "${YELLOW}   1. Set up remote: git remote add origin <repo-url>${NC}"
    echo -e "${YELLOW}   2. Set upstream: git push -u origin $BRANCH${NC}"
    exit 1
fi
