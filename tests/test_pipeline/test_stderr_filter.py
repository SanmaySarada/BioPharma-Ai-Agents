"""Tests for filter_r_stderr: strip R package loading noise, preserve real errors."""

from omni_agents.pipeline.stderr_filter import filter_r_stderr

# ---------------------------------------------------------------------------
# Test data: real R stderr samples
# ---------------------------------------------------------------------------

# tidyverse 2.0 banner with Unicode box-drawing chars, checkmarks, and crosses
TIDYVERSE_BANNER = (
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

# survminer loading block
SURVMINER_LOADING = (
    "Loading required package: ggplot2\n"
    "Loading required package: ggpubr\n"
    "\n"
    "Attaching package: 'survminer'\n"
    "The following object is masked from 'package:survival':\n"
    "\n"
    "    myeloma"
)

# dplyr standalone loading block
DPLYR_LOADING = (
    "Attaching package: 'dplyr'\n"
    "The following objects are masked from 'package:stats':\n"
    "\n"
    "    filter, lag\n"
    "The following objects are masked from 'package:base':\n"
    "\n"
    "    intersect, setdiff, setequal, union"
)

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

# Registered S3 method with continuation lines
REGISTERED_S3 = (
    "Registered S3 method overwritten by 'ggplot2':\n"
    "  method      from\n"
    "  print.ggproto"
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty() -> None:
    """filter_r_stderr('') returns ''."""
    assert filter_r_stderr("") == ""


def test_none_passthrough() -> None:
    """filter_r_stderr('') returns '' (empty string, since function takes str)."""
    assert filter_r_stderr("") == ""


def test_pure_error_preserved() -> None:
    """A pure error line is returned unchanged."""
    error = "Error in eval(expr) : object 'x' not found"
    assert filter_r_stderr(error) == error


def test_tidyverse_banner_stripped() -> None:
    """Full tidyverse 2.0 banner with Unicode is completely stripped."""
    result = filter_r_stderr(TIDYVERSE_BANNER)
    assert result == ""


def test_survminer_loading_stripped() -> None:
    """survminer loading block is completely stripped."""
    result = filter_r_stderr(SURVMINER_LOADING)
    assert result == ""


def test_dplyr_masked_objects_stripped() -> None:
    """dplyr loading block with masked objects is completely stripped."""
    result = filter_r_stderr(DPLYR_LOADING)
    assert result == ""


def test_real_error_with_survminer_tidyverse_noise() -> None:
    """Full combined stderr reduces to only the real error line."""
    result = filter_r_stderr(SURVMINER_TIDYVERSE_STDERR_WITH_ERROR)
    assert result == "Error in readRDS(con) : error reading from connection"
    assert "myeloma" not in result
    assert "Attaching" not in result
    assert "masks" not in result


def test_legitimate_warning_preserved() -> None:
    """Legitimate R warning is preserved unchanged."""
    warning = "Warning: NAs introduced by coercion"
    assert filter_r_stderr(warning) == warning


def test_legitimate_warning_in_sqrt_preserved() -> None:
    """Warning message with real warning body is preserved."""
    stderr = "Warning message:\nIn sqrt(x) : NaNs produced"
    result = filter_r_stderr(stderr)
    assert "In sqrt(x) : NaNs produced" in result


def test_registered_s3_stripped() -> None:
    """Registered S3 method and its continuation lines are stripped."""
    result = filter_r_stderr(REGISTERED_S3)
    assert result == ""


def test_mixed_noise_and_multiple_errors() -> None:
    """Noise lines are stripped but all error and warning lines are preserved."""
    stderr = (
        "Loading required package: ggplot2\n"
        "Error in foo() : bar\n"
        "Warning: baz"
    )
    result = filter_r_stderr(stderr)
    assert "Error in foo() : bar" in result
    assert "Warning: baz" in result
    assert "Loading required package" not in result


def test_leading_trailing_blank_lines_stripped() -> None:
    """Leading and trailing blank lines around an error are stripped."""
    stderr = "\n\n\nError in eval(expr) : oops\n\n\n"
    result = filter_r_stderr(stderr)
    assert result == "Error in eval(expr) : oops"


def test_error_lines_never_filtered() -> None:
    """Lines starting with 'Error' survive even if they contain noise-like words."""
    # "loading package" looks like noise but line starts with "Error" -- must survive
    error = "Error in loading package: test"
    assert filter_r_stderr(error) == error
