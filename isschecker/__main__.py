"""Entry point for ``python -m isschecker``."""

from isschecker import main

if __name__ == "__main__":
    # The console script gets this for free from setuptools; without it here,
    # `python -m isschecker` would exit 0 on a failing check.
    raise SystemExit(main())
