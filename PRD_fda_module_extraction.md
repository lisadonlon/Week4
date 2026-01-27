# PRD: FDA Medical Device Tool - Module Extraction

## Overview

This document defines the product requirements for extracting the FDA Medical Device Tool from the Medical Device Research Assistant into a standalone, reusable Python package. The goal is to make the FDA API wrapper available as an independent module that can be installed and used across multiple projects without carrying along Streamlit, OpenAI, or any other dependencies from the original application.

## Background

The current `FDA_tool.py` is the most self-contained and reusable component in the Medical Device Research Assistant project. It wraps the FDA Open API (api.fda.gov) and provides structured access to five medical device databases:

- **510(k)** clearances
- **PMA** (Premarket Approval) records
- **Recall** data
- **MAUDE** adverse event reports
- **Registration & Listing** facility data

However, it currently has coupling to Streamlit (debug output), hardcoded formatting assumptions (markdown output), and no packaging infrastructure. Extracting it into a proper package would make it usable in CLI tools, backend services, data pipelines, notebooks, and other applications.

### Current State

**File:** `FDA_tool.py` (429 lines, single class `FDAMedicalDeviceTool`)

**External dependencies:**
- `requests` (HTTP client) - necessary, stays
- `streamlit` (UI framework) - unnecessary coupling, must be removed
- Standard library: `typing`, `urllib.parse`, `json`, `traceback`

**Public API:**
- `FDAMedicalDeviceTool(debug_mode=False)`
- `run(query, database="all", limit=5) -> str`

**Current limitations preventing reuse:**
1. Imports `streamlit` at module level (`FDA_tool.py:4`) and in `_debug_print` (`FDA_tool.py:22`)
2. Returns only markdown-formatted strings; no access to raw structured data
3. No package structure (single file, no `setup.py` / `pyproject.toml`)
4. No type hints on return values
5. Debug output uses `print()` and Streamlit sidebar, not standard logging
6. No retry logic or rate limiting for FDA API calls
7. No caching for repeated queries
8. Query sanitization is minimal and database-specific field mapping is incomplete

---

## Goals

| # | Goal | Success Metric |
|---|------|---------------|
| G1 | Standalone package installable via `pip install` | `pip install fda-device-tools` works; no transitive Streamlit/OpenAI deps |
| G2 | Dual return format: raw data (dict/dataclass) and formatted text | Consumers can choose structured data or human-readable output |
| G3 | Zero non-essential dependencies | Only `requests` (or `httpx`) as external dependency |
| G4 | Usable in any Python context | Works in scripts, notebooks, Flask/FastAPI, CLI tools, data pipelines |
| G5 | Production-grade reliability | Retry logic, rate limiting, timeout configuration, proper logging |
| G6 | Clear documentation and examples | README with quickstart, API reference, and integration examples |

## Non-Goals

- Building a web UI (that stays in the parent project)
- Adding AI/LLM integration to the package (consumers bring their own)
- Supporting FDA APIs beyond medical devices (food, drugs, etc. are out of scope)
- Hosting or publishing the package to PyPI in this phase (local/GitHub install only)

---

## Requirements

### R1: Package Structure

Create a standalone Python package with the following layout:

```
fda-device-tools/
  pyproject.toml                  # Package metadata and build config
  README.md                       # Documentation
  LICENSE                         # License file
  src/
    fda_device_tools/
      __init__.py                 # Public API exports
      client.py                   # FDADeviceClient - main entry point
      databases.py                # Database enum and endpoint configuration
      models.py                   # Data models (dataclasses) for results
      formatters.py               # Output formatting (markdown, plain text, JSON)
      exceptions.py               # Custom exception hierarchy
      _http.py                    # HTTP layer with retry/timeout logic
  tests/
    __init__.py
    test_client.py
    test_formatters.py
    test_models.py
    test_http.py
    conftest.py                   # Shared fixtures, mock FDA API responses
  examples/
    basic_search.py
    multi_database_search.py
    pandas_integration.py
    agent_tool_integration.py     # Example showing how to wire into an LLM agent
```

**Acceptance criteria:**
- `pip install .` from the repo root installs the package
- `from fda_device_tools import FDADeviceClient` works after install
- No Streamlit, OpenAI, or other non-essential packages in dependency list

### R2: Core Client API

Redesign the public API around a client class with clear, typed methods:

```python
from fda_device_tools import FDADeviceClient, Database

client = FDADeviceClient()

# Search a specific database - returns structured data
results = client.search("insulin pump", database=Database.RECALL, limit=5)

# Access structured fields
for recall in results:
    print(recall.product_description)
    print(recall.reason)
    print(recall.classification)
    print(recall.date_initiated)

# Search all databases
all_results = client.search_all("cardiac stent", limit=3)
# Returns: {"510k": [...], "pma": [...], "recall": [...], "event": [...]}

# Get formatted output
formatted = client.search("insulin pump", database=Database.RECALL, format="markdown")
```

**Methods:**

| Method | Description | Returns |
|--------|------------|---------|
| `search(query, database, limit, format)` | Search a single FDA database | `list[ResultModel]` or `str` |
| `search_all(query, limit, format)` | Search across all device databases | `dict[str, list[ResultModel]]` or `str` |
| `search_510k(query, limit)` | Convenience method for 510(k) | `list[Clearance510k]` |
| `search_pma(query, limit)` | Convenience method for PMA | `list[PMAApproval]` |
| `search_recalls(query, limit)` | Convenience method for recalls | `list[Recall]` |
| `search_events(query, limit)` | Convenience method for adverse events | `list[AdverseEvent]` |
| `search_registrations(query, limit)` | Convenience method for registrations | `list[Registration]` |

**Acceptance criteria:**
- All five databases are accessible via dedicated convenience methods
- `format` parameter supports at minimum: `None` (structured data), `"markdown"`, `"json"`
- All methods have complete type hints
- All methods raise typed exceptions (not generic `Exception`)

### R3: Data Models

Define dataclasses for each database result type in `models.py`:

```python
@dataclass
class Clearance510k:
    device_name: str
    k_number: str
    manufacturer: str
    decision_date: str
    product_code: str
    device_class: str
    predicate_device: str | None
    summary: str | None
    raw: dict  # Original FDA API response for this record

@dataclass
class PMAApproval:
    device_name: str
    pma_number: str
    manufacturer: str
    approval_date: str
    product_code: str
    expedited_review: bool | None
    raw: dict

@dataclass
class Recall:
    product_description: str
    reason: str
    manufacturer: str
    date_initiated: str
    classification: str
    voluntary_mandated: str | None
    status: str | None
    raw: dict

@dataclass
class AdverseEvent:
    device_name: str
    manufacturer: str
    event_type: str
    report_date: str
    source_type: str | None
    device_problems: list[str]
    patient_outcomes: list[str]
    description: str | None
    raw: dict

@dataclass
class Registration:
    company_name: str
    registration_number: str
    address: str
    establishment_type: str | None
    product_codes: list[str]
    raw: dict
```

**Acceptance criteria:**
- Each model maps to one FDA database result type
- `raw` field preserves the original API response dict for fields not explicitly modeled
- Models are serializable to dict/JSON via a `.to_dict()` method
- Parsing logic handles missing/null fields gracefully (no `KeyError` on sparse results)

### R4: HTTP Layer

Create `_http.py` with production-grade HTTP handling:

- **Retry logic**: Automatic retry on 429 (rate limit) and 5xx errors with exponential backoff (3 attempts, 1s/2s/4s delays)
- **Timeout configuration**: Default 10-second timeout, configurable via `FDADeviceClient(timeout=15)`
- **Rate limiting**: Respect FDA API limits (240 requests per minute per IP for non-key users); optional API key support for higher limits
- **Session reuse**: Use `requests.Session()` for connection pooling
- **User-Agent**: Set a descriptive User-Agent header

**Acceptance criteria:**
- Transient server errors are retried automatically
- 429 responses are handled with appropriate backoff
- Timeout is configurable at client initialization
- FDA API key is optional but supported via `FDADeviceClient(api_key="...")`

### R5: Query Sanitization Improvements

Expand the current `_sanitize_query` logic:

- Support multi-word queries with proper quoting for the FDA API
- Add field mappings for all five databases (current code only maps 510k, recall, event)
- Handle special characters that break FDA API queries
- Support date range filters (e.g., recalls from the last 6 months)
- Provide a `raw_query` option to bypass sanitization for advanced users

**Acceptance criteria:**
- Queries with special characters (parentheses, colons, slashes) don't cause API errors
- All five databases have field-specific query optimization
- Date range filtering works for databases that support it
- `raw_query=True` passes the query string directly to the API

### R6: Formatters

Extract and improve the current markdown formatting into `formatters.py`:

- **Markdown formatter**: Produces the same markdown output as today (backwards compatible)
- **JSON formatter**: Returns `json.dumps()` of the structured data
- **Plain text formatter**: Simple text output for CLI usage
- **Dict formatter**: Returns Python dicts (for programmatic use without dataclass overhead)
- **Custom formatter support**: Accept a callable `formatter(results) -> str` for user-defined formats

**Acceptance criteria:**
- Default format returns structured data (dataclass instances)
- `format="markdown"` produces output equivalent to current `_format_*_results` methods
- Formatters are stateless functions that can be used independently

### R7: Exception Hierarchy

Define clear exceptions in `exceptions.py`:

```python
class FDAToolError(Exception):
    """Base exception for all FDA tool errors"""

class FDAAPIError(FDAToolError):
    """FDA API returned an error response"""
    status_code: int
    response_body: str

class FDATimeoutError(FDAToolError):
    """Request to FDA API timed out"""

class FDAQueryError(FDAToolError):
    """Invalid or unsupported query"""

class FDARateLimitError(FDAAPIError):
    """FDA API rate limit exceeded"""
```

**Acceptance criteria:**
- All exceptions inherit from `FDAToolError`
- API errors include status code and response body
- Consumers can catch `FDAToolError` for broad handling or specific types for targeted handling

### R8: Logging

Replace all `print()` and Streamlit debug output with Python `logging`:

- Module-level logger: `logger = logging.getLogger("fda_device_tools")`
- DEBUG: API request URLs, response status codes, query sanitization details
- INFO: Search initiated, results count
- WARNING: Empty results, retry attempts
- ERROR: API failures, parsing errors

**Acceptance criteria:**
- Zero `print()` statements in the package
- Zero Streamlit imports in the package
- Logging follows Python best practices (module-level logger, no root logger configuration)
- Consumers control log output via standard `logging.basicConfig()` or their own handler

### R9: Test Suite

Write tests covering the core functionality:

- **Unit tests**: Query sanitization, result parsing, formatting, model creation
- **Integration tests**: Mock FDA API responses to test full search flow
- **Edge cases**: Empty results, malformed API responses, network errors, special characters in queries

Use `pytest` and mock HTTP responses (no live API calls in tests).

**Acceptance criteria:**
- Tests run with `pytest` from the package root
- All formatters have at least one test per database type
- All models handle missing/null fields without errors
- HTTP retry logic is tested with mocked failure scenarios

### R10: Documentation

Write `README.md` with:

- Package overview and purpose
- Installation instructions (local install and from GitHub)
- Quickstart example (5 lines to first result)
- Full API reference for `FDADeviceClient`
- Database descriptions (what each database contains)
- Integration examples:
  - Basic Python script
  - Jupyter notebook usage
  - LLM agent tool integration (generic pattern, not OpenAI-specific)
  - FastAPI/Flask endpoint wrapping the tool
- Configuration options (timeout, API key, logging)

**Acceptance criteria:**
- README includes a working quickstart example
- All public methods are documented
- At least one integration example beyond basic usage

---

## Integration Back Into Parent Project

After extraction, the parent Medical Device Research Assistant should consume this package as a dependency:

```python
# In the parent project's tools/fda_tool.py (thin wrapper)
from fda_device_tools import FDADeviceClient, Database

client = FDADeviceClient(timeout=10)

def search_fda(query: str, database: str = "all", limit: int = 5) -> str:
    if database == "all":
        results = client.search_all(query, limit=limit, format="markdown")
    else:
        db = Database(database)
        results = client.search(query, database=db, limit=limit, format="markdown")
    return results
```

The parent project's `requirements.txt` would add:
```
fda-device-tools @ git+https://github.com/<user>/fda-device-tools.git
```

This keeps the parent project lean while the FDA tool evolves independently.

---

## Other Projects That Could Use This Module

The extracted package is useful anywhere FDA medical device data is needed:

| Use Case | How It Integrates |
|----------|------------------|
| **Regulatory compliance dashboards** | Backend data source for recall/clearance monitoring |
| **Medical device market research** | Programmatic access to 510(k) and PMA data for competitive analysis |
| **Post-market surveillance tools** | MAUDE adverse event monitoring and alerting |
| **Quality management systems** | Automated recall status checks |
| **LLM-powered research agents** | Drop-in tool for any agent framework (LangChain, CrewAI, OpenAI Agents SDK) |
| **Data science / notebooks** | Direct use in pandas workflows for FDA data analysis |
| **Slack/Teams bots** | Quick FDA lookups triggered by chat commands |

---

## Migration Plan

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| 1 | Create package skeleton (`pyproject.toml`, directory structure) | None |
| 2 | Port `FDAMedicalDeviceTool` logic into `client.py`, `_http.py`, `databases.py` | Phase 1 |
| 3 | Define data models in `models.py`, update parsers | Phase 2 |
| 4 | Extract formatters into `formatters.py` | Phase 3 |
| 5 | Add exception hierarchy and logging | Phases 2-4 |
| 6 | Write test suite with mocked API responses | Phases 2-5 |
| 7 | Write README and examples | Phases 2-6 |
| 8 | Update parent project to consume the extracted package | Phase 7 |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| FDA API changes endpoint structure or field names | Low | High | Pin known-working field names in models; `raw` field preserves full response |
| FDA API rate limits hit during heavy usage | Medium | Medium | Built-in rate limiting and optional API key support |
| Over-engineering the package for a narrow audience | Medium | Low | Start with the 5 existing databases; expand only on demand |
| Breaking the parent project during extraction | Medium | High | Keep the extraction as a copy-first, integrate-second process; parent project continues working until explicitly switched |

## Open Questions

1. **Package name**: Is `fda-device-tools` the right name, or something more specific/general?
2. **PyPI publishing**: Should this go on PyPI eventually, or stay as a GitHub-installable package?
3. **Async support**: Should the client offer async methods (via `httpx`) alongside sync, or sync-only for simplicity?
4. **FDA API key**: The FDA offers API keys for higher rate limits. Should key management be in scope for v1?
5. **Additional FDA datasets**: Should we plan for expansion to other FDA APIs (drugs, food) with a plugin architecture, or keep it device-focused?
