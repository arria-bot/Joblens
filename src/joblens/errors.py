"""Domain exceptions.

Libraries raise, the CLI decides how to print.  Keeping these distinct from
``ValueError`` lets the CLI report expected problems quietly and still treat
anything else as a bug.
"""


class JobLensError(Exception):
    """Base class for every expected JobLens failure."""


class ValidationError(JobLensError):
    """User input or extracted data failed validation."""


class NotFoundError(JobLensError):
    """A requested row does not exist."""


class AnalysisError(JobLensError):
    """Skill extraction failed (missing key, API error, unusable answer)."""
