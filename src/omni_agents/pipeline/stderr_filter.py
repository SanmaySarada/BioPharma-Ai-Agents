"""R stderr filtering: strip package loading noise, preserve real errors.

R prints verbose package loading messages to stderr when loading packages
like tidyverse, survminer, ggplot2. These messages consume the 500-char
truncation window and hide the actual error. This module strips them.

Applied once in execute_with_retry() before any stderr consumption.
"""


def filter_r_stderr(stderr: str) -> str:
    """Remove R package loading noise from stderr output.

    Strips lines matching known R package loading patterns while
    preserving actual errors, warnings, and diagnostic messages.

    Lines starting with 'Error' are NEVER filtered (safety net).

    Args:
        stderr: Raw stderr from R execution in Docker.

    Returns:
        Filtered stderr with package loading noise removed.
        Empty string if all content was noise.
    """
    return stderr  # Stub -- tests should fail
