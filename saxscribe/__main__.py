"""`python -m saxscribe ...` still works: it runs `python -m lift ...` (see __init__.py)."""
import sys

from lift.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
