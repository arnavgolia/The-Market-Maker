# Contributing to The Market Maker

## Development Setup

```bash
# Clone and setup
git clone <repo-url>
cd the-market-maker
make setup

# Install pre-commit hooks
pre-commit install
```

## Code Style

- **Formatting**: Black (100 char line length)
- **Linting**: Ruff
- **Type Checking**: mypy
- **Testing**: pytest

Run all checks:
```bash
make format
make lint
make typecheck
make test
```

## Testing Philosophy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Stress Tests**: Test under crisis conditions (10x spreads)

All tests must pass before committing.

## Adding New Strategies

1. Create strategy in `src/strategy/tier1/` (or tier2/tier3)
2. Inherit from `Strategy` base class
3. Implement `generate_signals()` method
4. Add regime gating (check `should_generate_signals()`)
5. Add tests in `tests/unit/`
6. Run walk-forward validation
7. Run stress tests (10x spreads)

## Adding New Features

1. **Design First**: Consider failure modes
2. **Add Tests**: Write tests before implementation
3. **Document**: Update README and docstrings
4. **Validate**: Run full test suite
5. **Review**: Get code review before merging

## Safety Guidelines

⚠️ **NEVER**:
- Disable kill rules
- Remove transaction cost modeling
- Skip walk-forward validation
- Use TIER_0 data for backtesting
- Remove watchdog independence

✅ **ALWAYS**:
- Test with paper trading first
- Monitor logs daily
- Review alerts
- Validate strategies before deployment
- Assume failure modes exist

## Commit Messages

Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `test:` Tests
- `refactor:` Code refactoring
- `chore:` Maintenance

Example:
```
feat: Add correlation-aware portfolio allocator

Implements correlation matrix calculation and adjusts position
sizes to reduce redundant risk exposure.
```

## Pull Request Process

1. Create feature branch
2. Implement changes with tests
3. Run full test suite
4. Update documentation
5. Submit PR with description
6. Address review feedback
7. Merge after approval

## Questions?

Open an issue or discussion for:
- Design questions
- Implementation help
- Bug reports
- Feature requests
