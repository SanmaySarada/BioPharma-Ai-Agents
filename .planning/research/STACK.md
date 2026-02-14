# Technology Stack: v1.2 Milestone Additions

**Project:** omni-ai-agents (Multi-LLM Clinical Trial Pipeline)
**Researched:** 2026-02-14
**Scope:** New libraries/approaches for v1.2 features only (protocol parser, CSR cleanup, interactive mode)
**Overall confidence:** HIGH

---

## Existing Stack Reference

These are already installed and integrated. Do NOT re-add or re-research:

| Package | Installed | Role |
|---------|-----------|------|
| python-docx | 1.2.0 | .docx read/write (used by R officer in Docker, available in Python) |
| openai | 2.20.0 | GPT-4o adapter (Track B) |
| google-genai | 1.62.0 | Gemini 2.5-pro adapter (Track A) |
| pydantic | 2.12.5 | Config models, data validation |
| typer | 0.21.2 | CLI framework |
| rich | 14.3.2 | Terminal display, Live panels |
| asyncio | stdlib | Pipeline orchestration |
| jinja2 | 3.1.6+ | Prompt templates |
| pyyaml | 6.0+ | Config loading |

---

## Feature A: Protocol Parser (.docx -> TrialConfig)

### Goal

Read a natural-language clinical trial protocol document (.docx), extract numeric parameters (n_subjects, visits, SBP means/SDs, dropout_rate, etc.) via LLM, and populate the existing `TrialConfig` Pydantic model.

### A1: Document Text Extraction

**Recommendation: python-docx (already installed, v1.2.0)** -- Confidence: HIGH

| Criterion | Assessment |
|-----------|------------|
| Already a dependency? | YES -- `python-docx>=1.1.0` in pyproject.toml, v1.2.0 installed |
| Extracts paragraphs? | YES -- `doc.paragraphs[i].text` |
| Extracts tables? | YES -- `doc.tables[i].rows[j].cells[k].text` |
| Extracts headers? | YES -- `doc.sections[i].header.paragraphs` |
| Python 3.13 compatible? | YES -- officially supports >=3.9 |
| Async? | N/A -- file I/O is fast, no need for async |

**Why python-docx and nothing else:**
- Already a project dependency. Zero new packages to add.
- Clinical trial protocols are structured Word documents with paragraphs, numbered sections, and occasional tables. python-docx handles all of these.
- The document is read once at pipeline start (not streamed), so performance is irrelevant.
- No need for docx2python or docx2txt -- those are simpler text-only extractors that lose structural information (headers, sections, table boundaries) that helps the LLM understand context.

**Implementation pattern:**

```python
from docx import Document

def extract_protocol_text(docx_path: Path) -> str:
    """Extract all text from a .docx protocol document.

    Preserves section structure by including paragraph styles
    and table boundaries as markers the LLM can parse.
    """
    doc = Document(str(docx_path))
    parts: list[str] = []

    for element in doc.element.body:
        if element.tag.endswith("p"):  # paragraph
            para = next(
                (p for p in doc.paragraphs if p._element is element), None
            )
            if para and para.text.strip():
                # Include heading level as context for the LLM
                style = para.style.name if para.style else ""
                if "Heading" in style:
                    parts.append(f"\n## {para.text}\n")
                else:
                    parts.append(para.text)
        elif element.tag.endswith("tbl"):  # table
            table = next(
                (t for t in doc.tables if t._element is element), None
            )
            if table:
                parts.append(_table_to_text(table))

    return "\n".join(parts)
```

**Alternatives NOT recommended:**

| Library | Why Not |
|---------|---------|
| docx2python | Loses paragraph style info (headings vs body). We need structure for LLM context. |
| docx2txt | Unmaintained, no table structure, just flattens everything. |
| mammoth | Converts to HTML -- unnecessary overhead when we just need text. |
| pypandoc | External binary dependency (pandoc). Overkill for text extraction. |

### A2: LLM Structured Data Extraction

**Recommendation: Use existing LLM adapters + SDK structured outputs** -- Confidence: HIGH

Both LLM SDKs already integrated in the project support structured output (JSON schema / Pydantic model) natively. No new libraries needed.

#### OpenAI Structured Outputs (GPT-4o)

The OpenAI SDK (v2.20.0, installed) supports `client.chat.completions.parse()` with a Pydantic model passed as `response_format`. The SDK converts the model to JSON schema, sends it, and deserializes the response automatically.

```python
# Async version -- works with existing AsyncOpenAI client
completion = await client.chat.completions.parse(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": protocol_text},
    ],
    response_format=TrialConfig,
)
extracted: TrialConfig = completion.choices[0].message.parsed
```

**Key constraint:** OpenAI structured outputs require all fields to be `required`. The existing `TrialConfig` uses defaults (e.g., `n_subjects: int = 300`), which is valid Pydantic but means OpenAI will always populate every field. This is actually desired behavior -- the LLM should extract all parameters or produce sensible defaults.

**Source:** [OpenAI Structured Outputs docs](https://platform.openai.com/docs/guides/structured-outputs), [openai-python helpers.md](https://github.com/openai/openai-python/blob/main/helpers.md)

#### Google Gemini Structured Outputs (Gemini 2.5-pro)

The google-genai SDK (v1.62.0, installed) supports structured output via `response_schema` in `GenerateContentConfig`. Pass a Pydantic model directly and access `response.parsed`.

```python
from google.genai import types

response = await client.aio.models.generate_content(
    model="gemini-2.5-pro",
    contents=protocol_text,
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=TrialConfig,
    ),
)
extracted: TrialConfig = response.parsed
```

**Key constraint:** Gemini requires `response_mime_type="application/json"` alongside `response_schema`. The SDK handles Pydantic model conversion internally.

**Source:** [Gemini Structured Output docs](https://ai.google.dev/gemini-api/docs/structured-output), [Gemini by Example](https://geminibyexample.com/020-structured-output/)

#### Architecture Decision: Extend BaseLLM or Create New Method?

**Recommendation: Add a `generate_structured()` method to `BaseLLM`.**

The existing `generate()` method returns `LLMResponse` with `raw_text` -- designed for R code extraction. The protocol parser needs typed output, not raw text. Adding a generic method keeps the abstraction clean:

```python
# In BaseLLM (base.py)
@abstractmethod
async def generate_structured[T: BaseModel](
    self, system_prompt: str, user_prompt: str, response_model: type[T]
) -> T:
    """Generate a structured response conforming to a Pydantic model."""
```

Each adapter implements this using its SDK's native structured output API. This avoids wrapping/unwrapping JSON manually and leverages the SDK's built-in schema enforcement.

**Alternatives NOT recommended:**

| Approach | Why Not |
|----------|---------|
| instructor library | Adds a dependency wrapping OpenAI/Gemini. Both SDKs already have native structured output. Extra abstraction layer with no benefit. |
| pydantic-ai | Full agent framework. Massive dependency for a single extraction call. Overkill. |
| Manual JSON parsing | Fragile. No schema enforcement. The SDKs do this natively and better. |
| LangChain output parsers | Massive dependency for one feature. The project intentionally avoids LangChain. |

---

## Feature B: CSR Data Dictionary Cleanup

### Goal

Move the data dictionary section out of the generated .docx Clinical Study Report into standalone files (YAML, CSV, or JSON).

### B1: No New Libraries Needed -- Confidence: HIGH

This is a **code restructuring** task, not a technology choice. The data dictionary content is currently embedded by the Medical Writer agent (via R officer package running in Docker). The fix involves:

1. Modifying the Medical Writer prompt template to output the data dictionary separately
2. Writing the dictionary to YAML/JSON using existing `pyyaml` or `json` (stdlib)
3. Optionally reading it back into python-docx if a reference section is still needed

**No new dependencies.** Use `pyyaml` (already installed) for human-readable data dictionary files, or `json` (stdlib) for machine-readable ones.

**Recommendation:** YAML format for data dictionaries because:
- Human-readable and editable
- Already used for project config (consistency)
- `pyyaml` is already a dependency

---

## Feature C: Interactive Execution Mode

### Goal

Add a `--interactive` / `--step` flag to the CLI that pauses the asyncio pipeline between steps, showing the user what happened and asking whether to continue.

### C1: Async-Compatible User Prompts

**Recommendation: `asyncio.to_thread()` wrapping `rich.prompt.Confirm.ask()`** -- Confidence: HIGH

| Approach | Adds Dependency? | Async-Compatible? | Works with Rich? | Complexity |
|----------|-------------------|--------------------|-------------------|------------|
| `asyncio.to_thread(Confirm.ask, ...)` | NO | YES | YES -- native Rich | Minimal |
| prompt-toolkit `prompt_async()` | YES (prompt-toolkit) | YES -- native | NO -- separate rendering | Medium |
| aioconsole `ainput()` | YES (aioconsole) | YES -- native | NO -- plain text | Medium |
| Raw `asyncio.to_thread(input, ...)` | NO | YES | NO -- no styling | Minimal |

**Why `asyncio.to_thread()` + Rich Confirm:**

1. **Zero new dependencies.** `asyncio.to_thread()` is stdlib (Python 3.9+). `rich.prompt.Confirm` is already installed.
2. **Visual consistency.** The pipeline already uses Rich for all display. Using Rich's `Confirm.ask()` gives styled yes/no prompts that match the existing UI.
3. **Simple integration.** The orchestrator's `_run_agent()` is async. Wrapping a blocking `Confirm.ask()` in `asyncio.to_thread()` is a one-liner that doesn't block the event loop.
4. **No Rich Live conflict.** The interactive mode would pause *between* steps, meaning `PipelineDisplay.stop()` is called before prompting and `start()` after the user confirms. No concurrent terminal rendering conflict.

**Implementation pattern:**

```python
import asyncio
from rich.prompt import Confirm

async def prompt_continue(step_name: str, console: Console) -> bool:
    """Ask user whether to continue after a completed step.

    Runs Rich's blocking Confirm.ask() in a thread to avoid
    blocking the asyncio event loop.
    """
    return await asyncio.to_thread(
        Confirm.ask,
        f"[bold]{step_name}[/bold] completed. Continue?",
        default=True,
        console=console,
    )
```

**Integration point in orchestrator:**

```python
# In PipelineOrchestrator.run(), after each step:
if self.interactive:
    self.display.stop()  # Pause Rich Live panel
    proceed = await prompt_continue("Simulator", self.console)
    if not proceed:
        raise typer.Exit(code=0)
    self.display.start()  # Resume Rich Live panel
```

**CLI flag addition (Typer):**

```python
@app.command()
def run(
    config: Path = _config_option,
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Pause between pipeline steps"
    ),
) -> None:
    ...
    orchestrator = PipelineOrchestrator(
        settings, callback=display, console=display.console,
        interactive=interactive,
    )
```

**Alternatives NOT recommended:**

| Library | Why Not |
|---------|---------|
| prompt-toolkit (v3.0.52) | Adds 3MB dependency. Has its own terminal rendering that conflicts with Rich Live. Would need to disable Rich display entirely during prompts. |
| aioconsole (v0.8.2) | Its own maintainer recommends prompt-toolkit instead for modern use. Adds dependency for something achievable with stdlib. |
| async-typer | Unnecessary wrapper. Typer already works with `asyncio.run()` as the project demonstrates. |
| Textual (TUI framework) | Nuclear option. Full TUI rewrite for a simple "continue? y/n" prompt. |

---

## New Dependencies Summary

### Required: NONE

All three v1.2 features can be implemented with zero new dependencies:

| Feature | Libraries Used | Status |
|---------|---------------|--------|
| Protocol parser: .docx reading | python-docx 1.2.0 | Already installed |
| Protocol parser: structured extraction | openai 2.20.0, google-genai 1.62.0 | Already installed |
| Protocol parser: config output | pydantic 2.12.5 | Already installed |
| CSR cleanup: dict output | pyyaml 6.0+ / json stdlib | Already installed |
| Interactive mode: async prompts | asyncio.to_thread (stdlib) + rich 14.3.2 | Already installed |

**This is the ideal outcome.** No new dependencies means:
- No version conflicts to manage
- No new security surface area
- No learning curve for unfamiliar libraries
- Faster CI/CD (no new downloads)

### Optional: Version Bumps to Consider

The project pins `>=` minimums in pyproject.toml. Current installed versions are recent. Potential bumps to consider if specific features are needed:

| Package | Current Min | Installed | Latest | Bump Needed? |
|---------|-------------|-----------|--------|--------------|
| google-genai | >=1.62.0 | 1.62.0 | 1.56.0* | NO -- installed version is ahead of PyPI latest (pre-release or local) |
| openai | >=2.17.0 | 2.20.0 | 2.21.0 | OPTIONAL -- 2.20.0 has structured outputs. 2.21.0 is cosmetic. |
| python-docx | >=1.1.0 | 1.2.0 | 1.2.0 | NO -- already at latest |

*Note: PyPI showed 1.56.0 as latest google-genai, but the project has 1.62.0 installed. This may be a pre-release or the search result was stale. The installed version supports structured output regardless.

---

## API Compatibility Notes

### TrialConfig as Structured Output Schema

The existing `TrialConfig` model works as a structured output schema for both providers, with one consideration:

```python
class TrialConfig(BaseModel):
    n_subjects: int = 300
    randomization_ratio: str = "2:1"
    seed: int = 12345
    visits: int = 26
    endpoint: str = "SBP"
    treatment_sbp_mean: float = 120.0
    # ... etc
```

**OpenAI:** All fields have defaults, so OpenAI will attempt to extract all of them. Fields the LLM cannot find in the protocol will get hallucinated values. **Mitigation:** Create a `ProtocolExtraction` model that wraps `TrialConfig` fields as `Optional[float]` with `None` defaults, then merge with `TrialConfig` defaults post-extraction. This lets the LLM signal "not found" vs "found value."

**Gemini:** Same consideration applies. Gemini's structured output produces syntactically valid JSON but does not guarantee semantic correctness.

**Recommended pattern:**

```python
class ProtocolExtraction(BaseModel):
    """What the LLM extracts from the protocol. None = not found."""
    n_subjects: int | None = None
    randomization_ratio: str | None = None
    visits: int | None = None
    endpoint: str | None = None
    treatment_sbp_mean: float | None = None
    treatment_sbp_sd: float | None = None
    placebo_sbp_mean: float | None = None
    placebo_sbp_sd: float | None = None
    baseline_sbp_mean: float | None = None
    baseline_sbp_sd: float | None = None
    age_mean: float | None = None
    age_sd: float | None = None
    missing_rate: float | None = None
    dropout_rate: float | None = None
    confidence_notes: dict[str, str] | None = None  # field -> "why I chose this value"

def merge_extraction(
    extraction: ProtocolExtraction,
    defaults: TrialConfig = TrialConfig(),
) -> TrialConfig:
    """Merge LLM extraction with defaults for missing fields."""
    overrides = {k: v for k, v in extraction.model_dump().items()
                 if v is not None and k != "confidence_notes"}
    return defaults.model_copy(update=overrides)
```

---

## Sources

### Verified (HIGH confidence)
- [python-docx 1.2.0 documentation](https://python-docx.readthedocs.io/) -- Tables, paragraphs, headers API
- [python-docx PyPI](https://pypi.org/project/python-docx/) -- Version 1.2.0, released 2025-06-16
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) -- Pydantic model support
- [openai-python helpers.md](https://github.com/openai/openai-python/blob/main/helpers.md) -- `parse()` method documentation
- [Gemini Structured Output docs](https://ai.google.dev/gemini-api/docs/structured-output) -- response_schema with Pydantic
- [Gemini by Example: Structured Output](https://geminibyexample.com/020-structured-output/) -- Code pattern with `response.parsed`
- [Rich Prompt docs](https://rich.readthedocs.io/en/stable/prompt.html) -- Confirm.ask() API
- [prompt-toolkit 3.0.52 asyncio docs](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/asyncio.html) -- prompt_async() reference (evaluated, not recommended)
- [aioconsole PyPI](https://pypi.org/project/aioconsole/) -- v0.8.2 evaluated, not recommended
- Installed package versions verified via `importlib.metadata` on 2026-02-14

### Cross-referenced (MEDIUM confidence)
- [Google Structured Outputs blog](https://blog.google/technology/developers/gemini-api-structured-outputs/) -- November 2025 JSON Schema expansion
- [openai-python GitHub issues](https://github.com/openai/openai-python/issues/1763) -- parse() edge cases

### Evaluated but not recommended
- [docx2python](https://github.com/ShayHill/docx2python) -- Alternative .docx extractor, loses heading structure
- [instructor](https://python.useinstructor.com/) -- LLM structured output wrapper, redundant with native SDK support
- [pydantic-ai](https://ai.pydantic.dev/) -- Full agent framework, massive overkill
