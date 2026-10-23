"""
ScholarFund AI
API key loading.

Keys are read from environment variables, or from a local .env file
(see .env.example). They are never hard-coded.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# The .env file sits at the project root, one level above this package.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class MissingApiKeyError(RuntimeError):
    pass


def get_api_key(name):
    """Return the API key stored in the environment variable `name`."""
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingApiKeyError(
            f"{name} is not set. Add it to the .env file "
            "(see .env.example)."
        )
    return value
