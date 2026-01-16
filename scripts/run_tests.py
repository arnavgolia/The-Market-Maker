#!/usr/bin/env python3
"""
Run all tests with pytest.

Usage:
    python scripts/run_tests.py                    # Run all tests
    python scripts/run_tests.py --unit              # Unit tests only
    python scripts/run_tests.py --integration       # Integration tests only
    python scripts/run_tests.py --stress            # Stress tests only
    python scripts/run_tests.py --coverage           # With coverage report
"""

import argparse
import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="Run test suite")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--stress", action="store_true", help="Run stress tests only")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Build pytest command
    cmd = ["pytest"]
    
    if args.unit:
        cmd.append("tests/unit/")
    elif args.integration:
        cmd.append("tests/integration/")
    elif args.stress:
        cmd.append("tests/stress/")
    else:
        cmd.append("tests/")
    
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    if args.coverage:
        cmd.extend(["--cov=src", "--cov=watchdog", "--cov=research", "--cov-report=html", "--cov-report=term"])
    
    # Run tests
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
