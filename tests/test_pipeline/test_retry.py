"""Tests for classify_error fixes and stderr filtering integration.

Verifies:
- ERRCLASS-01: "object 'x' not found" -> CODE_BUG, but "object is masked" -> not CODE_BUG
- ERRCLASS-02: "Error in " anchored regex (not broad "error in" substring)
- ERRCLASS-03: "could not find function" detection
- STDERR-03: filter_r_stderr + classify_error end-to-end on realistic R stderr
- ERRDSP-01/02: Filtered stderr fits within 500-char truncation window
"""

from omni_agents.models.execution import ErrorClassification
from omni_agents.pipeline.retry import classify_error
from omni_agents.pipeline.stderr_filter import filter_r_stderr

# ---------------------------------------------------------------------------
# Test data: realistic R stderr samples (independent copies -- don't import
# from test_stderr_filter.py to keep test files self-contained)
# ---------------------------------------------------------------------------

# Full combined stderr: survminer + tidyverse noise + a real error at the end
SURVMINER_TIDYVERSE_STDERR_WITH_ERROR = (
    "Loading required package: ggplot2\n"
    "Loading required package: ggpubr\n"
    "\n"
    "Attaching package: 'survminer'\n"
    "The following object is masked from 'package:survival':\n"
    "\n"
    "    myeloma\n"
    "\n"
    "\u2500\u2500 Attaching core tidyverse packages \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 tidyverse 2.0.0 \u2500\u2500\n"
    "\u2714 dplyr     1.1.0     \u2714 readr     2.1.4\n"
    "\u2714 forcats   1.0.0     \u2714 stringr   1.5.0\n"
    "\u2714 ggplot2   3.4.1     \u2714 tibble    3.1.8\n"
    "\u2714 lubridate 1.9.2     \u2714 tidyr     1.3.0\n"
    "\u2714 purrr     1.0.1\n"
    "\u2500\u2500 Conflicts \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 tidyverse_conflicts() \u2500\u2500\n"
    "\u2716 dplyr::filter() masks stats::filter()\n"
    "\u2716 dplyr::lag()    masks stats::lag()\n"
    "\u2139 Use the conflicted package (<http://conflicted.r-lib.org/>) to force all conflicts to become errors\n"
    "Error in readRDS(con) : error reading from connection"
)

# Only noise, no actual error
TIDYVERSE_NOISE_ONLY = (
    "\u2500\u2500 Attaching core tidyverse packages \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 tidyverse 2.0.0 \u2500\u2500\n"
    "\u2714 dplyr     1.1.0     \u2714 readr     2.1.4\n"
    "\u2714 forcats   1.0.0     \u2714 stringr   1.5.0\n"
    "\u2714 ggplot2   3.4.1     \u2714 tibble    3.1.8\n"
    "\u2714 lubridate 1.9.2     \u2714 tidyr     1.3.0\n"
    "\u2714 purrr     1.0.1\n"
    "\u2500\u2500 Conflicts \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 tidyverse_conflicts() \u2500\u2500\n"
    "\u2716 dplyr::filter() masks stats::filter()\n"
    "\u2716 dplyr::lag()    masks stats::lag()\n"
    "\u2139 Use the conflicted package (<http://conflicted.r-lib.org/>) to force all conflicts to become errors"
)


# ---------------------------------------------------------------------------
# Section 1: classify_error unit tests (ERRCLASS-01, ERRCLASS-02, ERRCLASS-03)
# ---------------------------------------------------------------------------


def test_classify_object_not_found_is_code_bug() -> None:
    """object 'x' not found -> CODE_BUG."""
    result = classify_error(
        "Error in eval(expr, envir, enclos) : object 'nonexistent_var' not found",
        1,
        False,
    )
    assert result == ErrorClassification.CODE_BUG


def test_classify_object_masked_not_code_bug() -> None:
    """CRITICAL: 'object is masked' noise must NOT be classified as CODE_BUG (ERRCLASS-01).

    With exit_code=0 and no actual error, this is just package loading noise.
    """
    masked_only = (
        "The following object is masked from 'package:survival':\n"
        "\n"
        "    myeloma"
    )
    result = classify_error(masked_only, 0, False)
    assert result == ErrorClassification.UNKNOWN


def test_classify_could_not_find_function() -> None:
    """could not find function -> CODE_BUG."""
    result = classify_error(
        "Error in library(nonexistent) : could not find function 'foo'",
        1,
        False,
    )
    assert result == ErrorClassification.CODE_BUG


def test_classify_unexpected_symbol() -> None:
    """unexpected symbol -> CODE_BUG."""
    result = classify_error(
        "Error: unexpected symbol in \"x y\"",
        1,
        False,
    )
    assert result == ErrorClassification.CODE_BUG


def test_classify_error_in_line_start() -> None:
    """Line starting with 'Error in' -> CODE_BUG (anchored regex)."""
    result = classify_error("Error in foo() : bar", 1, False)
    assert result == ErrorClassification.CODE_BUG


def test_classify_environment_error() -> None:
    """Missing package -> ENVIRONMENT_ERROR."""
    result = classify_error(
        "Error in library(nonexistent) : there is no package called 'nonexistent'",
        1,
        False,
    )
    assert result == ErrorClassification.ENVIRONMENT_ERROR


def test_classify_timeout() -> None:
    """Timed out execution -> TIMEOUT."""
    result = classify_error("", 1, True)
    assert result == ErrorClassification.TIMEOUT


def test_classify_empty_stderr_unknown() -> None:
    """Empty stderr with non-zero exit code -> UNKNOWN (graceful handling)."""
    result = classify_error("", 1, False)
    assert result == ErrorClassification.UNKNOWN


def test_classify_data_path_error() -> None:
    """Cannot open connection -> DATA_PATH_ERROR."""
    result = classify_error(
        "Error in file(file, \"rt\") : cannot open connection to '/data/missing.csv'",
        1,
        False,
    )
    assert result == ErrorClassification.DATA_PATH_ERROR


def test_classify_statistical_error() -> None:
    """Singular matrix -> STATISTICAL_ERROR."""
    result = classify_error(
        "Error in solve.default(t(x) %*% x) : system is computationally singular",
        1,
        False,
    )
    assert result == ErrorClassification.STATISTICAL_ERROR


# ---------------------------------------------------------------------------
# Section 2: End-to-end integration tests (STDERR-03, ERRDSP-01, ERRDSP-02)
# ---------------------------------------------------------------------------


def test_filtered_survminer_tidyverse_classified_correctly() -> None:
    """Full survminer+tidyverse noise with real error: filter then classify -> CODE_BUG.

    The classification must come from "Error in readRDS", NOT from false
    matching on "object is masked" (which was the ERRCLASS-01 bug).
    """
    filtered = filter_r_stderr(SURVMINER_TIDYVERSE_STDERR_WITH_ERROR)
    result = classify_error(filtered, 1, False)
    assert result == ErrorClassification.CODE_BUG
    # Verify the error line is what remains
    assert "Error in readRDS" in filtered
    # Verify noise is gone
    assert "myeloma" not in filtered
    assert "object is masked" not in filtered


def test_filtered_stderr_fits_truncation_window() -> None:
    """After filtering, the survminer+tidyverse stderr fits within 500 chars.

    This proves ERRDSP-02: the 500-char truncation window now contains
    the actual error instead of being consumed by package loading noise.
    """
    filtered = filter_r_stderr(SURVMINER_TIDYVERSE_STDERR_WITH_ERROR)
    assert len(filtered) < 500, (
        f"Filtered stderr is {len(filtered)} chars, exceeds 500-char window"
    )


def test_all_noise_no_error_classified_unknown() -> None:
    """Only noise (no error): after filtering, stderr is empty -> UNKNOWN.

    With exit_code=0, this is a successful run with noisy stderr.
    """
    filtered = filter_r_stderr(TIDYVERSE_NOISE_ONLY)
    assert filtered == ""
    result = classify_error(filtered, 0, False)
    assert result == ErrorClassification.UNKNOWN
