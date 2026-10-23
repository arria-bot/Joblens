"""JobLens: a CLI that compares a job posting's skills against yours."""

__version__ = "0.2.0"

from joblens.config import get_db_path

__all__ = ["__version__", "get_db_path"]
