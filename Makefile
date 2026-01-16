.PHONY: install install-dev install-research setup clean test lint format typecheck run-bot run-watchdog run-backtest help

# Colors for pretty output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

# Default Python
PYTHON := python3

help:
	@echo "$(BLUE)The Market Maker - Available Commands$(RESET)"
	@echo ""
	@echo "$(GREEN)Setup:$(RESET)"
	@echo "  make install          Install production dependencies"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make install-research Install research/notebook dependencies"
	@echo "  make setup            Full setup (venv + all deps + pre-commit)"
	@echo ""
	@echo "$(GREEN)Development:$(RESET)"
	@echo "  make test             Run test suite"
	@echo "  make test-stress      Run stress tests (10x spread scenarios)"
	@echo "  make lint             Run linter (ruff)"
	@echo "  make format           Format code (black + ruff)"
	@echo "  make typecheck        Run type checker (mypy)"
	@echo ""
	@echo "$(GREEN)Running:$(RESET)"
	@echo "  make run-bot          Start the trading bot"
	@echo "  make run-watchdog     Start the independent watchdog"
	@echo "  make run-backtest     Run backtesting suite"
	@echo ""
	@echo "$(GREEN)Maintenance:$(RESET)"
	@echo "  make clean            Remove build artifacts and caches"
	@echo "  make redis-start      Start Redis server (if not running)"
	@echo "  make redis-stop       Stop Redis server"

# ============================================================================
# SETUP
# ============================================================================

install:
	@echo "$(BLUE)Installing production dependencies...$(RESET)"
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

install-dev: install
	@echo "$(BLUE)Installing development dependencies...$(RESET)"
	$(PYTHON) -m pip install -e ".[dev]"
	pre-commit install

install-research: install
	@echo "$(BLUE)Installing research dependencies...$(RESET)"
	$(PYTHON) -m pip install -e ".[research]"

setup:
	@echo "$(BLUE)Full project setup...$(RESET)"
	$(PYTHON) -m venv .venv
	@echo "$(YELLOW)Activate venv with: source .venv/bin/activate$(RESET)"
	. .venv/bin/activate && $(MAKE) install-dev install-research
	@echo "$(GREEN)Setup complete!$(RESET)"

# ============================================================================
# DEVELOPMENT
# ============================================================================

test:
	@echo "$(BLUE)Running test suite...$(RESET)"
	pytest tests/ -v --tb=short

test-stress:
	@echo "$(BLUE)Running stress tests (10x spread scenarios)...$(RESET)"
	pytest tests/stress/ -v --tb=long

test-cov:
	@echo "$(BLUE)Running tests with coverage...$(RESET)"
	pytest tests/ --cov=src --cov=watchdog --cov-report=html --cov-report=term-missing

lint:
	@echo "$(BLUE)Running linter...$(RESET)"
	ruff check src/ watchdog/ tests/
	@echo "$(GREEN)Lint passed!$(RESET)"

format:
	@echo "$(BLUE)Formatting code...$(RESET)"
	black src/ watchdog/ tests/
	ruff check --fix src/ watchdog/ tests/
	@echo "$(GREEN)Formatting complete!$(RESET)"

typecheck:
	@echo "$(BLUE)Running type checker...$(RESET)"
	mypy src/ watchdog/

# ============================================================================
# RUNNING
# ============================================================================

run-bot:
	@echo "$(BLUE)Starting trading bot...$(RESET)"
	@echo "$(YELLOW)WARNING: Ensure watchdog is running separately!$(RESET)"
	$(PYTHON) scripts/run_bot.py

run-watchdog:
	@echo "$(BLUE)Starting independent watchdog...$(RESET)"
	@echo "$(RED)This MUST run in a separate terminal from the bot!$(RESET)"
	$(PYTHON) scripts/run_watchdog.py

run-backtest:
	@echo "$(BLUE)Running backtesting suite...$(RESET)"
	$(PYTHON) scripts/run_backtest.py

# ============================================================================
# REDIS
# ============================================================================

redis-start:
	@echo "$(BLUE)Starting Redis...$(RESET)"
	@if command -v redis-server > /dev/null; then \
		redis-server --daemonize yes; \
		echo "$(GREEN)Redis started$(RESET)"; \
	else \
		echo "$(RED)Redis not installed. Install with: brew install redis$(RESET)"; \
	fi

redis-stop:
	@echo "$(BLUE)Stopping Redis...$(RESET)"
	@redis-cli shutdown || echo "$(YELLOW)Redis not running$(RESET)"

redis-status:
	@redis-cli ping && echo "$(GREEN)Redis is running$(RESET)" || echo "$(RED)Redis is not running$(RESET)"

# ============================================================================
# CLEANUP
# ============================================================================

clean:
	@echo "$(BLUE)Cleaning build artifacts...$(RESET)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)Clean complete!$(RESET)"

clean-logs:
	@echo "$(BLUE)Cleaning log files...$(RESET)"
	rm -rf logs/*.log
	rm -rf logs/*.jsonl
	@echo "$(GREEN)Logs cleaned!$(RESET)"

clean-data:
	@echo "$(RED)WARNING: This will delete all local data!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && rm -rf data/*.db data/*.duckdb
