"""Tests for R code and JSON extraction from LLM responses."""

import pytest

from omni_agents.llm.response_parser import (
    contains_r_patterns,
    extract_json,
    extract_r_code,
)

# ---------------------------------------------------------------------------
# extract_r_code: fenced blocks with language tag
# ---------------------------------------------------------------------------


class TestFencedRBlocks:
    """Extraction from ```r ... ``` and ```R ... ``` blocks."""

    def test_lowercase_r_fence(self) -> None:
        response = (
            "Here is the code:\n"
            "```r\n"
            "library(survival)\n"
            "fit <- survfit(Surv(time, status) ~ group, data = df)\n"
            "```\n"
        )
        result = extract_r_code(response)
        assert result is not None
        assert "library(survival)" in result
        assert "survfit" in result

    def test_uppercase_r_fence(self) -> None:
        response = "```R\ndata <- read.csv('input.csv')\nsummary(data)\n```"
        result = extract_r_code(response)
        assert result is not None
        assert "read.csv" in result
        assert "summary(data)" in result

    def test_fence_with_trailing_whitespace_on_tag(self) -> None:
        response = "```r  \nx <- 1\n```"
        result = extract_r_code(response)
        assert result is not None
        assert "x <- 1" in result


# ---------------------------------------------------------------------------
# extract_r_code: untagged fenced blocks
# ---------------------------------------------------------------------------


class TestUntaggedFencedBlocks:
    """Extraction from ``` ... ``` blocks with no language tag."""

    def test_untagged_block_with_r_code(self) -> None:
        response = "```\nlibrary(dplyr)\ndf <- data.frame(x = 1:10)\n```"
        result = extract_r_code(response)
        assert result is not None
        assert "library(dplyr)" in result

    def test_untagged_block_without_r_code(self) -> None:
        """An untagged block that does not look like R should still be returned
        because the regex matches it (no language tag is still captured)."""
        response = "```\nsome random text\n```"
        result = extract_r_code(response)
        # The regex captures untagged blocks.  Since the content has no R
        # patterns, the block text is still returned (it was fenced).
        assert result is not None
        assert "some random text" in result


# ---------------------------------------------------------------------------
# extract_r_code: multiple blocks
# ---------------------------------------------------------------------------


class TestMultipleBlocks:
    """Multiple code blocks are concatenated in order."""

    def test_two_blocks_concatenated(self) -> None:
        response = (
            "First, load the library:\n"
            "```r\nlibrary(survival)\n```\n"
            "Now run the model:\n"
            "```r\nfit <- coxph(Surv(time, status) ~ age, data = lung)\n```\n"
        )
        result = extract_r_code(response)
        assert result is not None
        assert "library(survival)" in result
        assert "coxph" in result
        # Blocks separated by blank line
        parts = result.split("\n\n")
        assert len(parts) == 2

    def test_three_blocks_preserve_order(self) -> None:
        response = (
            "```r\n# step 1\n```\n"
            "some explanation\n"
            "```r\n# step 2\n```\n"
            "more text\n"
            "```r\n# step 3\n```\n"
        )
        result = extract_r_code(response)
        assert result is not None
        assert result.index("# step 1") < result.index("# step 2") < result.index("# step 3")

    def test_explanatory_text_between_blocks_is_stripped(self) -> None:
        response = (
            "Load libraries:\n"
            "```r\nlibrary(survival)\n```\n"
            "This loads the survival package for KM analysis.\n"
            "Now compute the model:\n"
            "```r\nfit <- survfit(Surv(time, status) ~ 1)\n```\n"
        )
        result = extract_r_code(response)
        assert result is not None
        assert "This loads the survival package" not in result
        assert "Now compute the model" not in result


# ---------------------------------------------------------------------------
# extract_r_code: pure R code (no fences)
# ---------------------------------------------------------------------------


class TestPureRCode:
    """When the LLM returns code without markdown fences."""

    def test_pure_r_code_returned(self) -> None:
        code = "library(ggplot2)\nggplot(mtcars, aes(x = mpg, y = hp)) + geom_point()"
        result = extract_r_code(code)
        assert result is not None
        assert "library(ggplot2)" in result

    def test_pure_r_with_assignment_arrow(self) -> None:
        code = "x <- 42\ny <- x + 1\ncat(y)"
        result = extract_r_code(code)
        assert result is not None
        assert "x <- 42" in result

    def test_pure_r_with_function_definition(self) -> None:
        code = "my_func <- function(a, b) {\n  return(a + b)\n}"
        result = extract_r_code(code)
        assert result is not None
        assert "function(a, b)" in result


# ---------------------------------------------------------------------------
# extract_r_code: no R code at all
# ---------------------------------------------------------------------------


class TestNoRCode:
    """When the response contains no recognizable R code."""

    def test_plain_english_returns_none(self) -> None:
        response = "I'm sorry, I cannot help with that request."
        result = extract_r_code(response)
        assert result is None

    def test_empty_string_returns_none(self) -> None:
        assert extract_r_code("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert extract_r_code("   \n\n  ") is None


# ---------------------------------------------------------------------------
# extract_r_code: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty blocks, nested backticks, mixed content."""

    def test_empty_code_block_skipped(self) -> None:
        response = "```r\n\n```\n```r\nx <- 1\n```"
        result = extract_r_code(response)
        assert result is not None
        assert "x <- 1" in result

    def test_all_empty_code_blocks_fall_through(self) -> None:
        """If all fenced blocks are empty, fall through to bare-text check."""
        response = "```r\n\n```\nlibrary(survival)"
        result = extract_r_code(response)
        assert result is not None
        # Falls through to bare-text detection because all blocks are empty
        assert "library(survival)" in result

    def test_code_block_with_backticks_inside(self) -> None:
        """A code block containing backtick strings inside R code."""
        response = '```r\nmsg <- "use `print()` here"\ncat(msg)\n```'
        result = extract_r_code(response)
        assert result is not None
        assert "msg" in result

    def test_mixed_tagged_and_untagged_blocks(self) -> None:
        response = (
            "```r\nlibrary(survival)\n```\n"
            "Then:\n"
            "```\nfit <- survfit(Surv(time, status) ~ 1)\n```\n"
        )
        result = extract_r_code(response)
        assert result is not None
        assert "library(survival)" in result
        assert "survfit" in result

    def test_single_line_code_block(self) -> None:
        response = "```r\nx <- 1\n```"
        result = extract_r_code(response)
        assert result is not None
        assert result == "x <- 1"


# ---------------------------------------------------------------------------
# contains_r_patterns
# ---------------------------------------------------------------------------


class TestContainsRPatterns:
    """Unit tests for the R pattern detection helper."""

    @pytest.mark.parametrize(
        "text",
        [
            "library(survival)",
            "x <- 42",
            "my_func <- function(a) { a + 1 }",
            "data.frame(x = 1:10)",
            "read.csv('file.csv')",
            "read_csv('file.csv')",
            "survfit(Surv(time, status) ~ 1)",
            "coxph(Surv(time, status) ~ age)",
        ],
    )
    def test_detects_r_patterns(self, text: str) -> None:
        assert contains_r_patterns(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Hello, world!",
            "x = 42",
            "def my_func(a): return a + 1",
            "import pandas as pd",
            "",
        ],
    )
    def test_rejects_non_r(self, text: str) -> None:
        assert contains_r_patterns(text) is False


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    """Tests for JSON extraction from LLM responses."""

    def test_json_in_fenced_block(self) -> None:
        response = '```json\n{"n_subjects": 300}\n```'
        result = extract_json(response)
        assert result == {"n_subjects": 300}

    def test_json_in_untagged_block(self) -> None:
        response = '```\n{"key": "value"}\n```'
        result = extract_json(response)
        assert result == {"key": "value"}

    def test_bare_json_object(self) -> None:
        response = 'Here is the data: {"x": 1, "y": 2} hope that helps'
        result = extract_json(response)
        assert result == {"x": 1, "y": 2}

    def test_json_with_surrounding_text(self) -> None:
        response = (
            "I analyzed the protocol and extracted the following:\n\n"
            '```json\n{"n_subjects": 500, "endpoint": "SBP"}\n```\n\n'
            "Let me know if you need anything else."
        )
        result = extract_json(response)
        assert result == {"n_subjects": 500, "endpoint": "SBP"}

    def test_nested_json(self) -> None:
        response = '```json\n{"trial": {"arms": ["treatment", "placebo"]}, "n": 300}\n```'
        result = extract_json(response)
        assert result == {"trial": {"arms": ["treatment", "placebo"]}, "n": 300}

    def test_no_json_returns_none(self) -> None:
        response = "This is just plain text with no JSON content at all."
        assert extract_json(response) is None

    def test_empty_string_returns_none(self) -> None:
        assert extract_json("") is None

    def test_invalid_json_in_fence_returns_none(self) -> None:
        response = '```json\n{invalid json content here\n```'
        assert extract_json(response) is None

    def test_multiple_json_blocks_returns_first(self) -> None:
        response = (
            '```json\n{"first": true}\n```\n'
            "Some text in between.\n"
            '```json\n{"second": true}\n```'
        )
        result = extract_json(response)
        assert result == {"first": True}
