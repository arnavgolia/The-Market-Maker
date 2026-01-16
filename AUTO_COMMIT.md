# 🔄 Auto-Commit Setup

The Market Maker now has automatic Git commit and push functionality!

## 🚀 Quick Start

After making changes, run:

```bash
# Option 1: Bash script
./scripts/auto_commit.sh

# Option 2: Python script
python scripts/git_auto_push.py
```

## ⚙️ Setup GitHub Remote

If you haven't set up a GitHub repository yet:

```bash
# 1. Create a new repo on GitHub (don't initialize with README)

# 2. Add remote
git remote add origin https://github.com/YOUR_USERNAME/The-Market-Maker.git

# 3. Push for the first time
git push -u origin main
```

## 🔧 Manual Usage

### Commit and push manually:

```bash
git add -A
git commit -m "Your commit message"
git push origin main
```

### Use auto-commit script:

```bash
./scripts/auto_commit.sh
```

## 📋 What Gets Committed

The scripts automatically:
- ✅ Stage all changes (respecting `.gitignore`)
- ✅ Generate smart commit messages based on changes
- ✅ Push to `origin/main` (or current branch)
- ✅ Skip if no changes exist

## 🚫 What Gets Ignored

The `.gitignore` ensures these are NOT committed:
- `.env` files (API keys)
- `*.log` files
- `data/` and `logs/` directories
- `__pycache__/` and Python cache files
- Database files (`.duckdb`, `.rdb`)

## 🎯 Commit Message Types

The script generates different messages based on changes:

- `✨ Update dashboard UI` - Dashboard changes
- `🎮 Add/update simulation mode` - Simulation features
- `🧪 Update tests` - Test files
- `⚙️  Update configuration` - Config changes
- `🔧 Update core functionality` - Python code
- `📝 Update documentation` - Markdown files
- `🔄 Auto-commit: timestamp` - Generic changes

## 🔄 Automatic Pushes

To enable automatic pushes after commits, set:

```bash
export AUTO_PUSH=true
```

Or add to your `.bashrc`/`.zshrc`:
```bash
export AUTO_PUSH=true
```

## ⚠️ Important Notes

1. **Never commit `.env` files** - They contain API keys
2. **Review changes** before pushing (use `git status`)
3. **Use meaningful commits** - Auto-commit is for convenience
4. **Check remote** - Make sure `origin` is set correctly

## 🐛 Troubleshooting

### "No remote 'origin' found"
```bash
git remote add origin https://github.com/YOUR_USERNAME/The-Market-Maker.git
```

### "Push failed"
```bash
# Set upstream branch
git push -u origin main
```

### "Nothing to commit"
- All changes are already committed
- Or all changes are ignored by `.gitignore`

## 📚 Git Best Practices

Even with auto-commit, follow these practices:

1. **Commit often** - Small, logical commits
2. **Write good messages** - Describe what changed
3. **Review before push** - Check `git diff` first
4. **Use branches** - For major features
5. **Keep `.env` safe** - Never commit secrets

Happy coding! 🚀
