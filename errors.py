"""Domain exceptions.

Library code raises these; only the CLI decides how to print them.
"""


class JobLensError(Exception):
    """Base class for all expected JobLens failures."""


class AnalysisError(JobLensError):
    """The skill-extraction step failed (missing key, bad JSON, API error...)."""


class NotFoundError(JobLensError):
    """A requested row does not exist."""
