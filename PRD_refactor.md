# PRD: Medical Device Research Assistant - Refactor

## Overview

This document defines the product requirements for refactoring the Medical Device Research Assistant from its current prototype state into a production-quality application with a cleaner architecture, better extensibility, and improved user experience.

## Background

The current project (4 files: `app2.py`, `agents.py`, `FDA_tool.py`, `requirements.txt`) is a working prototype that combines OpenAI GPT-4.1, FDA Open API data, DuckDuckGo web search, and OpenAI vector store document search into a Streamlit chat interface. It was built as a first coding project and has several structural issues that limit reliability, maintainability, and extensibility.

### Current Architecture

```
app2.py (Streamlit UI)
  -> imports Agent, Runner, WebSearchTool, FileSearchTool from agents.py
  -> imports FDAMedicalDeviceTool from FDA_tool.py
  -> manages session state, sidebar config, chat loop
```

### Key Problems to Address

1. **Dual agent framework**: `agents.py` defines custom `Agent`, `Runner`, `WebSearchTool`, and `FileSearchTool` classes that shadow the `agents` SDK package listed in `requirements.txt`. The app imports from the local `agents.py`, not the SDK. This creates confusion about which framework is actually in use.
2. **Hardcoded keyword routing**: Tool selection is driven by string matching against fixed keyword lists (`_needs_fda_search`, `_get_fda_search_params`), which is brittle and misses many valid queries.
3. **Redundant OpenAI client creation**: The OpenAI client is instantiated multiple times across files (`app2.py` startup test, `agents.py` in `_generate_response` and `WebSearchTool`, `FileSearchTool`). There is no shared client.
4. **No persistent state**: Conversation history lives only in Streamlit session state and is lost on page refresh.
5. **Debug artifacts in production code**: `print()` statements with emoji prefixes scattered throughout (`agents.py:139`, `agents.py:148`, `FDA_tool.py:111-112`).
6. **Tight Streamlit coupling in FDA tool**: `FDA_tool.py` imports `streamlit` directly for debug output, making it unusable outside a Streamlit context.
7. **File naming inconsistency**: `FDA_tool.py` uses uppercase/underscore while `app2.py` has a version suffix, suggesting iterative naming without cleanup.

---

## Goals

| # | Goal | Success Metric |
|---|------|---------------|
| G1 | Eliminate the dual-framework confusion by committing to one agent architecture | Single, clear import path for all agent/tool classes |
| G2 | Replace keyword-based tool routing with LLM-driven tool selection | Agent correctly routes 90%+ of novel queries without keyword lists |
| G3 | Centralize OpenAI client management | One client instance shared across all components |
| G4 | Remove all debug artifacts and Streamlit coupling from non-UI modules | `FDA_tool.py` and agent modules import zero UI libraries |
| G5 | Add conversation persistence | Chat history survives page refresh and is retrievable across sessions |
| G6 | Establish consistent project structure and naming | Clear directory layout with logical module separation |
| G7 | Improve error handling and user feedback | Errors surface actionable messages in the UI, not raw tracebacks |

## Non-Goals

- Migrating away from Streamlit (the UI framework stays)
- Adding new FDA databases or data sources (scope limited to refactoring existing functionality)
- User authentication or multi-tenancy (deferred to a future phase)
- Changing the underlying LLM provider (OpenAI stays)

---

## Requirements

### R1: Project Structure Reorganization

Restructure from a flat 4-file layout to a modular project:

```
medical-device-assistant/
  app.py                     # Streamlit entrypoint (renamed from app2.py)
  requirements.txt
  .env.example               # Template for required env vars
  config.py                  # Centralized configuration and client setup
  tools/
    __init__.py
    fda_tool.py              # FDA API wrapper (renamed, decoupled from Streamlit)
    web_search_tool.py       # DuckDuckGo search tool
    file_search_tool.py      # OpenAI vector store search tool
  agent/
    __init__.py
    assistant.py             # Agent definition and orchestration
  storage/
    __init__.py
    conversation.py          # Conversation persistence layer
```

**Acceptance criteria:**
- All imports resolve correctly
- No circular dependencies
- Each module has a single responsibility
- `tools/` modules have zero UI framework imports

### R2: Unified Agent Framework

Choose one of the following approaches and fully commit:

**Option A (Recommended): Use the OpenAI Agents SDK (`agents` package)**
- Remove the custom `Agent`, `Runner` classes from `agents.py`
- Define tools using the SDK's `@function_tool` decorator or `FunctionTool` class
- Let the SDK handle tool routing via the model's native function-calling
- Removes `_needs_fda_search()`, `_get_fda_search_params()`, and all hardcoded keyword lists

**Option B: Fully custom agent (drop the `agents` SDK dependency)**
- Remove `agents` from `requirements.txt`
- Upgrade the custom `Agent` class to use OpenAI function-calling API directly
- Define tool schemas as JSON and let the model select tools
- Still removes hardcoded keyword routing

**Acceptance criteria:**
- One agent framework in use, clearly documented
- No shadowed imports between local modules and external packages
- Tool routing is model-driven, not keyword-driven
- The `_needs_fda_search`, `_get_fda_search_params`, and `_find_tool_by_name` methods are removed

### R3: Centralized Configuration

Create `config.py` to own all configuration and shared resources:

- Load environment variables (`OPENAI_API_KEY`, `vector_store_id`) once
- Validate required config at startup with clear error messages
- Create and export a single OpenAI client instance
- Expose model name and other settings as constants

**Acceptance criteria:**
- No other module calls `os.environ` or `load_dotenv` directly
- No other module instantiates `openai.OpenAI()`
- Missing config raises a clear error at startup, not mid-conversation
- `.env.example` documents all required variables

### R4: FDA Tool Decoupling

Refactor `FDA_tool.py` → `tools/fda_tool.py`:

- Remove `import streamlit` and all Streamlit-specific debug output
- Replace `_debug_print` with standard Python `logging` module
- Accept a logger instance or use module-level logger
- Remove all bare `print()` debug statements
- Keep the public API (`run(query, database, limit)`) unchanged
- Add a tool schema/description for agent framework integration

**Acceptance criteria:**
- `tools/fda_tool.py` can be imported and used in a plain Python script with no Streamlit dependency
- Debug output uses `logging` at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- All existing FDA database coverage (510k, PMA, recall, event, registrationlisting) is preserved

### R5: Conversation Persistence

Implement `storage/conversation.py` with a lightweight persistence layer:

- Store conversations in SQLite (zero additional infrastructure)
- Schema: `conversations` table (id, created_at, updated_at) and `messages` table (id, conversation_id, role, content, timestamp)
- Provide functions: `save_message()`, `load_conversation()`, `list_conversations()`, `delete_conversation()`
- Integrate with Streamlit session state so history loads on page refresh

**Acceptance criteria:**
- Refreshing the browser page restores the current conversation
- Sidebar shows a list of past conversations that can be resumed
- Conversations can be deleted
- SQLite file is stored in a configurable path (default: `./data/conversations.db`)

### R6: Error Handling Cleanup

Standardize error handling across all modules:

- Replace bare `except:` blocks (e.g., `FDA_tool.py:348`) with specific exception types
- Remove `traceback.format_exc()` from user-facing output; log it instead
- Define consistent error response format for tools: `{"error": True, "message": "...", "source": "tool_name"}`
- Surface user-friendly messages in the chat UI; detailed errors go to logs only

**Acceptance criteria:**
- No bare `except:` or `except Exception` blocks without logging
- User never sees a raw Python traceback in the chat interface
- All errors are logged with sufficient context for debugging

### R7: UI Cleanup

Refactor `app2.py` → `app.py`:

- Remove version suffix from filename
- Remove the startup OpenAI client test block (`app2.py:20-26`); config validation handles this
- Remove the debug directory creation at the bottom of the file (`app2.py:216-218`)
- Clean up the async wrapper (consider `st.cache_resource` for the agent)
- Consolidate session state initialization into a single function

**Acceptance criteria:**
- `app.py` is under 150 lines
- No debug/test code in the UI module
- Session state initialization is in one place
- Sidebar configuration is cleanly separated from main chat logic

---

## Migration Plan

This refactor should be done incrementally to avoid a broken state:

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| 1 | Create project structure, `config.py`, `.env.example` | None |
| 2 | Decouple FDA tool (R4) - remove Streamlit imports, add logging | Phase 1 |
| 3 | Unify agent framework (R2) - choose approach, implement | Phase 1 |
| 4 | Migrate web search and file search tools into `tools/` | Phases 2-3 |
| 5 | Add conversation persistence (R5) | Phase 1 |
| 6 | Refactor UI (R7) and error handling (R6) | Phases 3-5 |
| 7 | End-to-end testing and cleanup | All phases |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| OpenAI Agents SDK has breaking API changes | Medium | High | Pin SDK version; wrap SDK calls in thin adapter |
| SQLite locks under concurrent Streamlit sessions | Low | Medium | Use WAL mode; single-writer pattern |
| Refactored tool routing behaves differently than keyword matching | Medium | Medium | Test with the example queries already defined in the sidebar |
| Migration breaks existing workflows mid-refactor | Medium | High | Phase incrementally; keep app functional after each phase |

## Open Questions

1. **Agents SDK vs. custom**: Should we commit to the `agents` SDK or go fully custom? The SDK provides native tool-calling but adds a dependency. A custom approach gives full control but requires more code.
2. **Conversation export**: Should the persistence layer support exporting conversations (e.g., to PDF or markdown) in this phase, or defer?
3. **Testing**: Should this refactor include a test suite, or is that a separate effort? The current project has no tests.
