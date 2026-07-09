"""Bazel py_test entry point: run pytest over the test files passed as args."""

import sys

import pytest

if __name__ == "__main__":
    # Args are the specific test file(s) for this target, injected by the
    # py_test `args` attribute; fall back to quiet discovery.
    sys.exit(pytest.main(sys.argv[1:] or ["-q"]))
