"""Entry point for BrewPi-Serial-REST."""

import sys
from .brewpi_rest import main

if __name__ == "__main__":
    sys.exit(main())