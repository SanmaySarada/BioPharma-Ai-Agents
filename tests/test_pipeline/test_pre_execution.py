"""Tests for pre-execution R code validation.

Verifies:
- ALLOWED_PACKAGES stays in sync with the Docker image's installed packages
- ALLOWED_PACKAGES covers every package listed in prompt templates
- Pre-execution validation catches disallowed packages
"""

import re
from pathlib import Path

from omni_agents.pipeline.pre_execution import ALLOWED_PACKAGES, validate_r_code

# Packages explicitly installed in docker/r-clinical/Dockerfile's install.packages() call.
# Tidyverse sub-packages (dplyr, tidyr, etc.) are implicitly installed via tidyverse.
DOCKERFILE_PACKAGES: frozenset[str] = frozenset({
    "survival", "survminer", "tidyverse", "haven", "jsonlite",
    "readr", "ggplot2", "broom", "tableone", "officer", "flextable",
    "writexl",
})

# Tidyverse sub-packages that are allowed but not explicitly in the Dockerfile
TIDYVERSE_SUB_PACKAGES: frozenset[str] = frozenset({
    "dplyr", "tidyr", "stringr", "purrr", "tibble", "forcats", "lubridate",
})


# ---------------------------------------------------------------------------
# Consistency checks
# ---------------------------------------------------------------------------


def test_allowed_packages_covers_dockerfile() -> None:
    """Every package in the Dockerfile install list must be in ALLOWED_PACKAGES."""
    missing = DOCKERFILE_PACKAGES - ALLOWED_PACKAGES
    assert not missing, (
        f"Dockerfile packages missing from ALLOWED_PACKAGES: {sorted(missing)}. "
        f"Add them to pre_execution.py"
    )


def test_allowed_packages_no_unknown() -> None:
    """Every ALLOWED_PACKAGES entry should be in the Dockerfile or a tidyverse sub-package."""
    known = DOCKERFILE_PACKAGES | TIDYVERSE_SUB_PACKAGES
    unknown = ALLOWED_PACKAGES - known
    assert not unknown, (
        f"ALLOWED_PACKAGES contains packages not in Dockerfile or tidyverse: "
        f"{sorted(unknown)}"
    )


def test_prompt_templates_only_use_allowed_packages() -> None:
    """Every package listed in a prompt template's 'Available R Packages' section
    must be in ALLOWED_PACKAGES.

    This prevents the bug where a prompt tells the LLM to use a package
    that the pre-execution validator would flag or Docker doesn't have.
    """
    templates_dir = (
        Path(__file__).parent.parent.parent
        / "src" / "omni_agents" / "templates" / "prompts"
    )
    # Match lines like "- packagename (functions)" or "- packagename"
    pkg_pattern = re.compile(r"^-\s+(\w+)\s*(?:\(|$)", re.MULTILINE)

    issues: list[str] = []
    for template in sorted(templates_dir.glob("*.j2")):
        text = template.read_text()
        # Only check within the "Available R Packages" section
        section_start = text.find("## Available R Packages")
        if section_start == -1:
            continue
        # Section ends at the next ## heading or end of file
        section_end = text.find("\n## ", section_start + 1)
        if section_end == -1:
            section_end = len(text)
        section = text[section_start:section_end]

        for match in pkg_pattern.finditer(section):
            pkg = match.group(1)
            if pkg not in ALLOWED_PACKAGES:
                issues.append(f"{template.name}: '{pkg}' not in ALLOWED_PACKAGES")

    assert not issues, (
        "Prompt templates reference packages not in ALLOWED_PACKAGES:\n"
        + "\n".join(f"  - {i}" for i in issues)
    )


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def test_validate_catches_disallowed_package() -> None:
    """validate_r_code flags library() calls for packages not in allowed set."""
    code = 'library(writexl)\nwrite_xlsx(df, "out.xlsx")'
    issues = validate_r_code(code, [], [], allowed_packages=frozenset({"tidyverse"}))
    assert any("writexl" in i for i in issues)


def test_validate_allows_known_package() -> None:
    """validate_r_code does not flag allowed packages."""
    code = 'library(writexl)\nwrite_xlsx(df, "out.xlsx")'
    issues = validate_r_code(code, [], [])
    pkg_issues = [i for i in issues if "DISALLOWED_PACKAGE" in i]
    assert not pkg_issues, f"writexl should be allowed but got: {pkg_issues}"


def test_validate_catches_install_packages() -> None:
    """validate_r_code flags install.packages() calls."""
    code = 'install.packages("foo")\nlibrary(tidyverse)'
    issues = validate_r_code(code, [], [])
    assert any("INSTALL_PACKAGES" in i for i in issues)


def test_validate_catches_missing_output_ref() -> None:
    """validate_r_code flags missing expected output references."""
    code = 'library(tidyverse)\nwrite.csv(df, "ADSL.csv")'
    issues = validate_r_code(code, [], ["ADTTE.rds"])
    assert any("ADTTE.rds" in i for i in issues)
