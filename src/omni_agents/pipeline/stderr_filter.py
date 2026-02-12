"""R stderr filtering: strip package loading noise, preserve real errors.

R prints verbose package loading messages to stderr when loading packages
like tidyverse, survminer, ggplot2. These messages consume the 500-char
truncation window and hide the actual error. This module strips them.

Applied once in execute_with_retry() before any stderr consumption.
"""

import re

# Compiled regex patterns matching R package loading noise lines.
# Order does not matter -- each line is tested against all patterns.
_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # tidyverse banner line: "-- Attaching core tidyverse packages ..."
    re.compile(r"Attaching (core )?tidyverse packages?", re.IGNORECASE),
    # Conflicts header line (with box-drawing chars or dashes)
    re.compile(r"Conflicts\s*[\u2500-\u257f-]+"),
    # Package conflict line: "x dplyr::filter() masks stats::filter()"
    re.compile(r"\w+::\w+\(\)\s+masks\s+\w+::\w+\(\)"),
    # Object masking header: "The following object(s) is/are masked from ..."
    re.compile(r"The following objects?\s+(is|are)\s+masked\s+from", re.IGNORECASE),
    # Loading required package: ...
    re.compile(r"^Loading required package:\s", re.IGNORECASE),
    # Attaching package: ...
    re.compile(r"^Attaching package:\s", re.IGNORECASE),
    # Checkmark/bullet/info lines from tidyverse (e.g., "v ggplot2 3.4.1")
    re.compile(r"^[\u2714\u2716\u2713\u2717\u2022\u2139]"),
    # Info line about conflicted package
    re.compile(r"Use the conflicted package", re.IGNORECASE),
    # Registered S3 method overwritten
    re.compile(r"^Registered S3 method", re.IGNORECASE),
    # Indented continuation: object names after "masked from" line,
    # or indented method table rows after "Registered S3 method" line.
    re.compile(r"^\s{2,}[\w.,\s]+$"),
    # "also loading:" messages
    re.compile(r"^also loading:", re.IGNORECASE),
    # Box-drawing decoration lines (only decoration, no text content)
    re.compile(r"^[\u2500-\u257f\s-]+$"),
    # "replacing previous import" warnings from package loading
    re.compile(r"replacing previous import"),
)


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
    if not stderr:
        return ""

    filtered_lines: list[str] = []
    for line in stderr.splitlines():
        # Safety: never filter lines starting with Error/error
        stripped = line.strip()
        if stripped.startswith("Error") or stripped.startswith("error"):
            filtered_lines.append(line)
            continue

        # Check against noise patterns
        if any(p.search(line) for p in _NOISE_PATTERNS):
            continue

        filtered_lines.append(line)

    # Strip leading/trailing blank lines from filtered output
    return "\n".join(filtered_lines).strip()
