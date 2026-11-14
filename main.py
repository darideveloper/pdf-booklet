#!/usr/bin/env python3
"""Entry point: ``python3 main.py book.pdf``, same CLI as ``python3 booklet.py``."""

import sys

from booklet import main

if __name__ == "__main__":
    sys.exit(main())
