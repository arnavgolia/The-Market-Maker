#!/usr/bin/env python3
"""
Auto-commit and push script for The Market Maker.

This script automatically commits and pushes changes to GitHub.
Run this after making important changes, or set it up as a git hook.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

def run_command(cmd, check=True):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip(), e.returncode

def get_changed_files():
    """Get list of changed files."""
    stdout, _, _ = run_command("git diff --name-only HEAD", check=False)
    staged_stdout, _, _ = run_command("git diff --cached --name-only", check=False)
    
    changed = [f for f in stdout.split('\n') if f]
    staged = [f for f in staged_stdout.split('\n') if f]
    
    return changed + staged

def generate_commit_message(files):
    """Generate commit message based on changed files."""
    files_str = ' '.join(files).lower()
    
    if 'dashboard' in files_str:
        return "✨ Update dashboard UI and features"
    elif 'simulation' in files_str:
        return "🎮 Add/update simulation mode"
    elif 'test' in files_str:
        return "🧪 Update tests"
    elif 'config' in files_str:
        return "⚙️  Update configuration"
    elif any(f.endswith('.py') for f in files):
        return "🔧 Update core functionality"
    elif any(f.endswith('.md') for f in files) or 'readme' in files_str:
        return "📝 Update documentation"
    else:
        return f"🔄 Auto-commit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def main():
    """Main function."""
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    
    print("🔄 Auto-commit script starting...")
    
    # Check if git is initialized
    if not (repo_root / ".git").exists():
        print("❌ Not a git repository. Initializing...")
        run_command("git init")
        print("✅ Git repository initialized")
    
    # Check for changes
    stdout, _, code = run_command("git diff --quiet && git diff --cached --quiet", check=False)
    if code == 0:
        print("ℹ️  No changes to commit")
        return 0
    
    # Get changed files
    changed_files = get_changed_files()
    
    # Generate commit message
    commit_msg = generate_commit_message(changed_files)
    
    # Stage all changes
    print("📦 Staging changes...")
    run_command("git add -A")
    
    # Show status
    print("📋 Changes to commit:")
    stdout, _, _ = run_command("git status --short", check=False)
    print(stdout)
    
    # Commit
    print(f"💾 Committing: {commit_msg}")
    stdout, stderr, code = run_command(f'git commit -m "{commit_msg}"', check=False)
    if code != 0:
        if "nothing to commit" in stderr.lower():
            print("ℹ️  Nothing to commit")
            return 0
        print(f"❌ Commit failed: {stderr}")
        return 1
    
    # Get current branch
    stdout, _, _ = run_command("git branch --show-current", check=False)
    branch = stdout or "main"
    
    # Push
    print(f"🚀 Pushing to origin/{branch}...")
    stdout, stderr, code = run_command(f"git push origin {branch}", check=False)
    if code != 0:
        if "no upstream branch" in stderr.lower():
            print("⚠️  No upstream branch. Setting up...")
            run_command(f"git push -u origin {branch}")
        elif "remote" in stderr.lower() and "not found" in stderr.lower():
            print("❌ Remote 'origin' not found.")
            print("   Please add remote: git remote add origin <repo-url>")
            return 1
        else:
            print(f"❌ Push failed: {stderr}")
            return 1
    
    print("✅ Successfully pushed to GitHub!")
    print(f"   Commit: {commit_msg}")
    return 0

if __name__ == "__main__":
    import os
    sys.exit(main())
