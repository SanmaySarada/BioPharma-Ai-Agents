"""Pre-execution R code validation via regex.

Catches obvious R code issues before wasting a Docker execution (ERRH-05).
Checks for disallowed packages, install.packages() calls, and missing
references to expected input/output files.
"""

import re

# Packages known to be pre-installed in the r-clinical Docker image
ALLOWED_PACKAGES: frozenset[str] = frozenset({
    "survival", "survminer", "tidyverse", "haven", "jsonlite",
    "readr", "ggplot2", "broom", "tableone", "dplyr", "tidyr",
    "stringr", "purrr", "tibble", "forcats", "lubridate",
    "officer", "flextable", "writexl",
})

# Regex patterns for R library/require calls
_LIBRARY_RE = re.compile(r"""(?:library|require)\(\s*["']?(\w+)["']?\s*\)""")
_INSTALL_RE = re.compile(r"""install\.packages\s*\(""")


class PreExecutionError(Exception):
    """Raised when pre-execution R code validation finds issues.

    Attributes:
        issues: List of human-readable issue descriptions.
    """

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        issue_list = "\n".join(f"  - {issue}" for issue in issues)
        message = (
            f"Pre-execution validation failed "
            f"({len(issues)} issue{'s' if len(issues) != 1 else ''}):\n{issue_list}"
        )
        super().__init__(message)


def validate_r_code(
    code: str,
    expected_inputs: list[str],
    expected_outputs: list[str],
    allowed_packages: frozenset[str] = ALLOWED_PACKAGES,
) -> list[str]:
    """Validate R code before Docker execution.

    Returns a list of issue strings (empty means code is OK).

    Checks:
    - All library()/require() packages are in the allowed set
    - No install.packages() calls (packages are pre-installed)
    - All expected input file paths appear in the code
    - All expected output file paths appear in the code

    Args:
        code: The R code string to validate.
        expected_inputs: File paths that should appear in the code as inputs.
        expected_outputs: File paths that should appear in the code as outputs.
        allowed_packages: Set of packages allowed for use (default: ALLOWED_PACKAGES).

    Returns:
        List of issue strings. Empty list means no issues found.
    """
    issues: list[str] = []

    # Check library/require calls against allowed packages
    for match in _LIBRARY_RE.finditer(code):
        pkg = match.group(1)
        if pkg not in allowed_packages:
            issues.append(
                f"DISALLOWED_PACKAGE: '{pkg}' not in allowed list"
            )

    # Check for install.packages() calls
    if _INSTALL_RE.search(code):
        issues.append(
            "INSTALL_PACKAGES: code tries to install packages "
            "(all packages are pre-installed)"
        )

    # Check expected input file references
    for input_ref in expected_inputs:
        if input_ref not in code:
            issues.append(
                f"MISSING_INPUT_REF: code does not reference '{input_ref}'"
            )

    # Check expected output file references
    for output_ref in expected_outputs:
        if output_ref not in code:
            issues.append(
                f"MISSING_OUTPUT_REF: code does not reference '{output_ref}'"
            )

    return issues


def check_r_code(
    code: str,
    expected_inputs: list[str],
    expected_outputs: list[str],
) -> None:
    """Validate R code and raise PreExecutionError if issues found.

    Convenience wrapper around validate_r_code that raises on failure.

    Args:
        code: The R code string to validate.
        expected_inputs: File paths that should appear in the code as inputs.
        expected_outputs: File paths that should appear in the code as outputs.

    Raises:
        PreExecutionError: If any validation issues are found.
    """
    issues = validate_r_code(code, expected_inputs, expected_outputs)
    if issues:
        raise PreExecutionError(issues)
