# Design Rationale

This document explains the technical decisions made while building the Transaction Dispute Resolution Agent, including the reasoning, trade-offs, and alternatives considered.

---

## Table of Contents

1. [Framework Selection: Why LangChain?](#1-framework-selection-why-langchain)
2. [PII Masking Strategy: Why Two Layers?](#2-pii-masking-strategy-why-two-layers)
3. [LLM Provider Selection: Demo-Focused Choice with Model Abstraction](#3-llm-provider-selection-demo-focused-choice-with-model-abstraction)
4. [Agent Pattern: Why ReAct?](#4-agent-pattern-why-react)
5. [User Context: Why Session-Based Context Variables?](#5-user-context-why-session-based-context-variables)
6. [Storage: Why JSON Files?](#6-storage-why-json-files)
7. [Configuration: Why Pydantic Settings?](#7-configuration-why-pydantic-settings)
8. [Fuzzy Matching: Why Configurable Thresholds?](#8-fuzzy-matching-why-configurable-thresholds)
9. [Security: Why Input Sanitization + Prompt Hardening?](#9-security-why-input-sanitization--prompt-hardening)
10. [Resilience: Why Retry + Rate Limiting + Circuit Breaker?](#10-resilience-why-retry--rate-limiting--circuit-breaker)
11. [Mock Data: Why 30 Curated Transactions?](#11-mock-data-why-30-curated-transactions)
12. [Tool Design: Why Separate Tools Instead of One Generic Tool?](#12-tool-design-why-separate-tools-instead-of-one-generic-tool)
13. [Future Improvements](#future-improvements)

---

## 1. Framework Selection: Why LangChain?

### Available Options

When building LLM-powered agents, there are several popular frameworks:

| Framework | Strength | Best For |
|-----------|----------|----------|
| **LangGraph** | Maximum control, graph-based workflows | Complex custom workflows |
| **LangChain** | Balance of control and pre-built features | Production agents with common patterns |
| **CrewAI** | Easy multi-agent setup | Multi-agent collaboration |
| **AutoGen** | Multi-agent conversations, shared state | Conversational agent teams |

### Why Not LangGraph?

LangGraph provides the most control as you can create custom graphs and define exact node transitions. However, you have to develop everything from scratch - there are no pre-built components for common patterns like PII redaction, summarization, or tool middleware. It's essentially low-level code where you're responsible for implementing every feature.

Six months ago, I would have chosen LangGraph because the control was worth the extra development effort. But things have changed.

### Why Not CrewAI or AutoGen?

CrewAI and AutoGen are optimized for multi-agent workflows where multiple agents collaborate on tasks. They're excellent for scenarios like "researcher agent gathers data, analyst agent processes it, writer agent creates report."

For this project, I have a single agent handling transaction disputes. The multi-agent overhead would add complexity without benefit. Additionally, CrewAI abstracts away agent internals, making debugging harder when issues arise.

### Why LangChain v1?

LangChain v1 introduced significant improvements:

1. **`create_agent` function**: Uses the same ReAct pattern under the hood but provides a clean, high-level API
2. **Middleware system**: Game-changer for cross-cutting concerns like PII redaction, logging, and validation
3. **`init_chat_model`**: Provider-agnostic model initialization - switch between Gemini, OpenAI, Groq with one parameter
4. **Built-in patterns**: Summarization, memory management, tool validation out of the box

**Example of the middleware benefit:**
```python
# Without middleware: modify every tool, add try/catch everywhere
# With middleware: declare once, applies to all interactions
self.agent = create_agent(
    model=self.llm,
    tools=self.tools,
    middleware=[
        PIIMiddleware("email", strategy="redact"),
        PIIMiddleware("credit_card", strategy="redact"),
    ],
)
```

### Trade-off Acknowledged

The main caveat with LangChain v1 is its newness. There are fewer Stack Overflow threads and community resources. I encountered some functionality gaps and had to read the actual library source code to understand certain behaviors (like how middleware chains work internally). This is acceptable for a project where I can invest time in understanding the framework deeply.

---

## 2. PII Masking Strategy: Why Two Layers?

### The Architecture

I implemented PII masking at two points:
1. **Before sending to agent**: Custom `mask_pii()` function in `src/utils/pii.py`
This function uses a hybrid approach: it applies regex-based masking first, followed by Microsoft Presidio masking. The final output is the fully redacted text.

2. **Inside agent**: LangChain's `PIIMiddleware` for tool outputs

### Why Not Just Middleware?

At first glance, middleware alone should be sufficient. LangChain's `PIIMiddleware` is called:
- Before the model sees the input
- After the model generates output
- Before tools receive input
- After tools return output

So PII should be redacted at every step, right?

### The Observability Problem

The issue becomes visible when you set up proper traceability. In production, we need audit trails and observability. When I configured LangSmith (LangChain's tracing platform), I discovered something important:

**LangSmith logs the input and output of each middleware call separately.**

Here's what appears in LangSmith traces:

```
Human message: My email is john@example.com and card is 4532-0151-1283-0366 and my SSN is 555-50-1234.

Email PII Middleware:
  Input:  My email is john@example.com and card is 4532-0151-1283-0366 and my SSN is 555-50-1234.
  Output: My email is [REDACTED_EMAIL] and card is 4532-0151-1283-0366 and my SSN is 555-50-1234.

CreditCard PII Middleware:
  Input:  My email is [REDACTED_EMAIL] and card is 4532-0151-1283-0366 and my SSN is 555-50-1234.
  Output: My email is [REDACTED_EMAIL] and card is [REDACTED_CREDIT_CARD] and my SSN is 555-50-1234.

SSN PII Middleware:
  Input:  My email is [REDACTED_EMAIL] and card is [REDACTED_CREDIT_CARD] and my SSN is 555-50-1234.
  Output: My email is [REDACTED_EMAIL] and card is [REDACTED_CREDIT_CARD] and my SSN is [REDACTED_SSN].
```

**The original PII is captured in the audit logs** because middleware logging shows the "before" state at each step. For financial applications, this is a compliance issue - PII shouldn't appear in any logs.

### The Solution

By applying custom PII masking before the message even enters the agent:

```python
# In process_message()
masked_input = mask_pii(sanitized.text)  # Mask BEFORE agent
self.messages.append(HumanMessage(content=masked_input))
result = self._invoke_agent(self.messages)
```

Now LangSmith only ever sees `[REDACTED_EMAIL]` - the original value never enters the system.

### Why Keep PII Middleware Then?

Once we mask user input before it reaches the agent, input-level middleware becomes largely redundant. However, I kept the middleware for demonstration purposes, since I am not calling the mask_pii function inside the tools as the mock data does not contain any real PII.

The agent can invoke tools that fetch data from storage. If production transaction data contains PII (such as emails or credit card details), the middleware will redact it before the LLM processes it. However, this introduces the same logging concern: unmasked data may still appear in logs before redaction occurs.

**To address this, we have two options:**
1. Update the logging mechanism to ensure sensitive data is never logged in raw form, or
2. Apply a custom mask_pii function inside each tool so that outputs are already sanitized before being returned.

With the second approach, the middleware can either be removed entirely or retained as a safety net, depending on whether the additional latency (a few milliseconds) is acceptable.

**Trade-offs**:
- Custom masking: Ensures sensitive data never appears in logs, but requires adding masking logic to every tool and before sending input to the agent.
-  Middleware: Acts as a centralized safety net for any PII missed by custom masking, at the cost of minimal additional latency.

---

## 3. LLM Provider Selection: Demo-Focused Choice with Model Abstraction

### The Decision

The primary goal of this project is to demonstrate agent behavior, tool orchestration, middleware, and safety mechanisms, rather than the raw reasoning capabilities of a specific language model.

For that reason, I intentionally chose free and easily accessible models (Groq and Gemini) for the demo, while designing the system to remain fully model-agnostic using LangChain’s init_chat_model abstraction.

### Why This Approach

The focus of the project is on:
- Agent architecture
- Middleware-based safety (PII handling)
- Tool invocation and control flow
- Observability and debuggability

Using state-of-the-art or paid models would not meaningfully improve the demonstration of these architectural concepts. Instead, it would introduce unnecessary cost and complexity during development and review.

### Why Groq Was Used for the Demo

Groq was selected primarily for practical demo reasons:
- Free and fast: Allows rapid iteration and live demos without incurring cost
- Low latency: Sub-second responses make agent execution feel responsive
- Sufficient capability: Fully adequate for demonstrating tool usage and middleware behavior

The choice of Groq is not a reflection of model superiority, but rather a pragmatic decision to showcase system functionality without distractions.

### Why Gemini Is Also Supported

Gemini is supported as an alternative provider to demonstrate provider flexibility, not as a required dependency.

This demonstrates that the system can adapt to different providers without architectural changes.


Model-Agnostic Design via Abstraction

The system uses LangChain’s init_chat_model, which ensures that:
- Switching providers is a configuration change, not a code change
- The agent logic remains independent of the underlying model
- Future models or providers can be integrated easily

```
llm = init_chat_model(
    model="llama-3.3-70b-versatile",  # or "gemini-1.5-flash"
    model_provider="groq",            # or "google_genai"
)
```

This abstraction allows the project to focus on architecture and behavior, rather than being tied to a specific vendor or model.

### Trade-offs

Different models have slightly different behaviors when it comes to:
- Tool calling formats
- Prompt sensitivity
- Response verbosity

---

## 4. Agent Pattern: Why ReAct?

### What is ReAct?

ReAct (Reasoning + Acting) is an agent pattern where the LLM:
1. **Reasons** about what to do next
2. **Acts** by calling a tool
3. **Observes** the result
4. **Repeats** until the task is complete

### Why ReAct Over Direct Function Calling?

**Direct function calling** would be: Parse query → Call tool → Return result. It's faster and cheaper but:
- No ability to handle unexpected situations
- Cannot ask follow-up questions
- Cannot combine multiple tool calls intelligently

**ReAct enables:**
- "I found 3 transactions matching that amount. Let me ask which one..."
- "The merchant name didn't match, but let me search by amount and date instead..."
- "I'll get the transaction details first, then fetch merchant info to explain it..."

### Why Not a Fixed Pipeline?

A fixed pipeline like `extract_query → search_transactions → format_response` breaks on edge cases:
- What if the user asks about a dispute status, not a transaction?
- What if multiple transactions match and we need clarification?
- What if the merchant isn't found but similar ones exist?

ReAct handles these dynamically because the LLM decides the next step based on context.

### The Trade-off

ReAct uses more tokens (the reasoning steps cost money) and is slightly slower. For a dispute resolution agent where accuracy matters more than speed, this is acceptable. A high-volume, simple query system might choose direct function calling instead.

---

## 5. User Context: Why Session-Based Context Variables?

### The Problem

Tools need to know which user is making the request. The naive approach is passing `user_id` as a parameter to every tool:

```python
@tool
def get_transactions(user_id: str, amount: float = None):
    ...
```

But this has problems:
1. The LLM must remember to pass `user_id` every time
2. The LLM might hallucinate or mix up user IDs
3. Security risk: LLM could be manipulated to access other users' data

### The Solution: Context Variables

I use Python's `contextvars` to store the current user ID in thread-local storage:

```python
# Set once when session starts
set_current_user_id("user_001")

# Tools read from context - no parameter needed
@tool
def get_transactions(amount: float = None):
    user_id = get_current_user_id()  # Always gets the right user
    ...
```

### Benefits

1. **Security**: User ID is set at session start and cannot be changed by the LLM
2. **Cleaner tools**: LLM only needs to worry about query parameters, not identity
3. **Testability**: Tests can set different user contexts easily
4. **No hallucination risk**: User ID is never in the prompt for LLM to misremember

### Production Environment

In production environment, the user ID would be fetched from the database after the user performs the authentication.

---

## 6. Storage: Why JSON Files?

### The Decision

All data is stored in JSON files:
- `data/transactions.json` - Transaction records
- `data/merchants.json` - Merchant information
- `data/sessions/{user_id}.json` - Conversation history
- `data/disputes/{dispute_id}.json` - Filed disputes

### Why Not a Database?

For a demo/interview project, JSON files offer:
1. **Zero setup**: No database installation or configuration
2. **Inspectability**: Open the file and see the data immediately
3. **Portability**: Clone the repo and it works
4. **Version control friendly**: Can commit sample data

### The Trade-off

JSON files don't support:
- Concurrent access (fine for single-user demo)
- Complex queries (acceptable for small dataset)
- Transactions/ACID guarantees

### Production Path

The `Storage` class abstracts file operations. Migrating to PostgreSQL would mean:
1. Replace `_read_json`/`_write_json` with database queries
2. Keep the same interface (`get_transactions`, `save_dispute`, etc.)
3. No changes to agent or tools code (if using same data structure)

---

## 7. Configuration: Why Pydantic Settings?

### The Decision

All configuration uses Pydantic Settings (`pydantic-settings` package):

```python
class Settings(BaseSettings):
    llm_provider: Literal["gemini", "groq"] = Field(
        default="groq", description="LLM provider to use (gemini or groq)"
    )
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    gemini_model: str = Field(
        default="gemini-1.5-flash", description="Gemini model to use"
    )

    model_config = SettingsConfigDict(env_file=".env")
```

### Why Pydantic Settings Over Plain Environment Variables?

1. **Type validation**: `amount_tolerance_percent` must be a float - fails at startup if invalid
2. **Defaults**: Sensible defaults with explicit documentation
3. **IDE support**: Autocomplete and type hints for all settings
4. **Single source of truth**: All configuration in one place
5. **Environment file support**: Native `.env` file loading

### Why Not YAML/JSON Config Files?

- No type validation at load time
- Easy to have mismatched types
- No IDE support
- Another file format to manage

### Example of Type Safety Benefit

```python
# With plain env vars - fails silently or at runtime
tolerance = float(os.getenv("AMOUNT_TOLERANCE", "ten"))  # Crashes later

# With Pydantic - fails at startup with clear error
# ValidationError: amount_tolerance_percent - value is not a valid float
```

---

## 8. Fuzzy Matching: Why Configurable Thresholds?

### 1. Fuzzy Matching

#### The Problem

Users rarely remember transaction details exactly. In practice:
- “About fifty dollars” might correspond to $49.99 or $52.00
- A remembered date such as “last Tuesday” may be off by a day or two

If the system relies on exact matching, the agent may correctly invoke a tool, but the tool will return no results. This leads to a poor user experience where the user is told that no matching transactions exist, even though relevant transactions are present in the data.

#### The Decision

To address this, the system uses **fuzzy matching** when filtering transactions. Instead of requiring exact equality, the tool allows a tolerance around values such as amount and date.

For example:
- A user query for `$50` can still match a transaction of `$49.99`
- A date query can match transactions within a nearby range

This ensures that user intent is respected even when the input is imprecise.

### 2. Configurable Thresholds

#### Why Thresholds Are Configurable

The acceptable level of fuzziness varies by context and deployment:

- A premium banking application may require high precision
- A consumer-facing application may prioritize recall and user convenience

For this reason, tolerance values are **not hardcoded**. Instead, they are configurable at runtime.

Example defaults:
- **Amount tolerance**: ±10%
- **Date tolerance**: ±3 days

These values can be adjusted without code changes:

```python
AMOUNT_TOLERANCE_PERCENT=10.0
DATE_TOLERANCE_DAYS=3
```

---

## 9. Security: Why Input Sanitization + Prompt Hardening?

### Defense in Depth

I implemented two security layers:

1. **Input Sanitization** (`src/agent/security.py`):
   - Remove dangerous characters (null bytes, escape sequences)
   - Detect prompt injection patterns ("ignore previous instructions")
   - Truncate extremely long inputs

2. **Prompt Hardening** (system prompt):
   - Explicit instructions to stay on topic
   - Instructions to never reveal system prompt
   - Instructions to handle manipulation attempts professionally

### Why Both?

**Sanitization alone** might miss sophisticated attacks that don't match patterns.

**Prompt hardening alone** relies on the LLM following instructions - which isn't guaranteed, especially with clever prompt injections.

Together, they provide:
- Sanitization catches known attack patterns before LLM sees them
- Hardening guides LLM behavior for attacks that slip through
- Audit logging captures all attempts for security review

### Why Not Block Suspicious Input?

I considered blocking flagged inputs entirely, but:
- Legitimate queries might contain flagged patterns ("ignore" is a normal word)
- Blocking frustrates users without explanation
- Better to log the attempt and let hardened prompt handle it

### Production Environment
The current sanitization is primarily intended to demonstrate that, in real-world systems, sanitization techniques are required to mitigate prompt-injection risks. Additional scenarios and rules can be added to make the system production-ready.

Sanitization and prompt hardening do **not guarantee** complete protection against prompt injection. There are complementary approaches, such as training a small language model (SLM) or classifier to detect prompt-injection attempts before the prompt is forwarded to the agent.

An early IBM paper provides useful insights into this approach:
https://www.ibm.com/think/insights/prevent-prompt-injection

From a security perspective, the user_id is resolved inside the tool itself. This ensures that the agent can only access transactions belonging to the authenticated user, and the LLM does not have the ability to select or query data for arbitrary users.

For a production environment, my recommendation would be to:
- Train a dedicated classifier to detect prompt-injection attempts
- Combine this with strict prompt hardening and input sanitization rules

This layered approach significantly improves the overall security posture of the system.

---

## 10. Resilience: Why Retry + Rate Limiting + Circuit Breaker?

### The Problem

LLM APIs are external services that can:
- Fail temporarily (network issues)
- Rate limit (too many requests)
- Have outages (provider issues)

### The Solution: Three Patterns

1. **Retry with Exponential Backoff**
   - Transient failures often succeed on retry
   - Backoff prevents hammering a struggling service
   - Max 3 attempts by default

2. **Rate Limiting (Token Bucket)**
   - Prevents hitting provider rate limits
   - 60 requests/minute by default
   - Queues requests instead of failing

3. **Circuit Breaker**
   - If 5 consecutive failures: stop trying for 60 seconds
   - Prevents cascade failures during outages
   - Fails fast with clear error instead of timeout

### Why All Three?

| Pattern | Handles |
|---------|---------|
| Retry | Transient failures (network blips) |
| Rate Limit | Client-side prevention of 429 errors |
| Circuit Breaker | Sustained outages |

They complement each other - retry handles blips, rate limit prevents self-inflicted 429s, circuit breaker handles outages.

### The Trade-off

Added complexity and latency for resilience. For a demo, this might seem overkill, but it demonstrates production thinking and the patterns are reusable.

---

## 11. Mock Data: Why 30 Curated Transactions?

### The Decision

I created 30 transactions covering specific scenarios rather than generating random data.

Curated data ensures I can demonstrate:
- Exact match scenario
- Fuzzy amount match ($48.50 vs "fifty dollars")
- Fuzzy date match (actual Wednesday vs "last Tuesday")
- Multiple matches (two Netflix charges)
- Merchant aliases ("AMZN MKTP" when user says "Amazon")
- International transactions (EUR, GBP)
- Different statuses (pending, posted, refunded)

### Why 30?

- **Manageable**: Can verify all data manually
- **Enough variety**: Covers all demo scenarios
- **Memorable**: Can remember key transactions for demos

---

## 12. Tool Design: Why Separate Tools Instead of One Generic Tool?

### The Decision

I created separate tools for each operation:
- `get_transactions` - Search with filters
- `get_transaction_by_id` - Direct lookup
- `get_merchant_info` - Merchant details
- `search_merchant_by_name` - Merchant search
- `flag_for_review` - Create dispute
- `get_dispute_status` - Check dispute

### Why Not One Generic Tool?

A single `query_database(sql: str)` tool would be:
- **Security risk**: LLM could craft malicious queries
- **Prompt injection vector**: User input in SQL
- **Hard to validate**: Any query structure possible

### Benefits of Separate Tools

1. **Constrained inputs**: Each tool has specific, validated parameters
2. **Clear semantics**: LLM knows exactly what each tool does
3. **Easier prompting**: "Use get_transactions to search" is clearer than "Write a query"
4. **Security**: Can't access data outside defined operations
5. **Testability**: Each tool can be unit tested independently

### The Trade-off

More tools to maintain and document. But the security and clarity benefits outweigh the maintenance cost.

---

## Summary

| Decision | Rationale |
|----------|-----------|
| LangChain v1 | Best balance of control and pre-built features (middleware, init_chat_model) |
| Two-layer PII | Observability tools log middleware internals; must mask before agent |
| Provider abstraction | Flexibility, cost optimization, availability |
| ReAct pattern | Handles edge cases, follow-ups, dynamic tool combinations |
| Context variables | Security (LLM can't change user), cleaner tool signatures |
| JSON storage | Zero setup, inspectable, portable; abstracted for easy migration |
| Pydantic Settings | Type safety, defaults, IDE support, single source of truth |
| Configurable thresholds | Tunable without code changes, auditable matching logic |
| Sanitization + hardening | Defense in depth; neither alone is sufficient |
| Full resilience patterns | Handles transient failures, rate limits, outages |
| Curated mock data | Predictable demos, covers all edge cases |
| Separate tools | Security, validation, clear semantics |

Each decision balances demo simplicity with production thinking, demonstrating awareness of real-world requirements while keeping implementation manageable.

---

## Future Improvements

The following enhancements would improve the system for production readiness:

### 1. Fuzzy Matching for Merchant Names

Currently, merchant matching relies on exact substring matching against names and aliases. This can fail when:
- User says "Starbux" but the merchant is "Starbucks"
- User says "Amazon Prime" but the alias is "AMZN MKTP"

**Improvement**: Implement fuzzy string matching (e.g., Levenshtein distance, Jaro-Winkler similarity) for merchant name lookups. This would allow queries like "Starbux" to match "Starbucks" with a configurable similarity threshold.

### 2. Cleaner Tool Output for User-Facing Responses

The current tool responses include internal details that are not meaningful to end users:

```
**Merchant Overview – Netflix**

| Attribute | Details |
|-----------|---------|
| **Merchant ID** | `merch_003` |
| **Name** | Netflix |
| **Category** | Subscription – streaming entertainment |
```

**Improvement**: Create separate response formatters that filter out internal fields (like `merchant_id`, `transaction_id`) when presenting information to users. The LLM should receive clean, user-friendly data that it can relay directly.

### 3. FastAPI Setup with Authentication

The current CLI interface is suitable for demos but not for production deployment.

**Improvement**: Add a FastAPI-based REST API with:
- JWT or OAuth2 authentication
- WebSocket support for streaming responses
- Rate limiting per user/API key
- Health check and metrics endpoints
- OpenAPI documentation

### 4. Custom PII Detection in Middleware

Currently, the middleware uses LangChain's built-in PII detection. For financial applications, we may need domain-specific detection.

**Improvement**: Replace or augment the middleware with custom Presidio-based detection that can identify:
- Account numbers in specific formats
- Internal reference numbers
- Domain-specific identifiers

This would use the same `detect_all_pii()` function already implemented in `src/utils/pii.py`.

### 5. Add More Middlewares To Improve Agent Robustness

As the agent grows in complexity, failures can occur due to excessive tool calls, transient model errors, or suboptimal tool selection.

Improvement: Introduce additional middlewares to better control and harden the agent. These would:
- Tool call limit: Control tool execution by limiting the number of tool calls per request
- Model fallback: Automatically switch to alternative models when the primary model fails
- LLM-based tool selector: Use a lightweight LLM to pre-select relevant tools before invoking the main model
- Tool retry: Automatically retry failed tool calls using exponential backoff
- Model retry: Automatically retry failed model calls using exponential backoff

This layered middleware approach increases reliability, prevents runaway execution, and improves overall agent robustness.

### 6. Streaming Responses

Currently, the agent returns complete responses after processing. For complex queries with multiple tool calls, this can feel slow.

**Improvement**: Implement streaming responses so users see partial output as the agent reasons and acts. LangChain supports streaming out of the box with `stream()` instead of `invoke()`.

### 7. Multi-Language Support

The current system only supports English queries and responses.

**Improvement**: Add i18n support for:
- System prompts in multiple languages
- Date/currency formatting based on locale
- PII detection patterns for different regions (e.g., IBAN for Europe, different SSN formats)

### 8. Analytics and Feedback Loop

Currently, there's no mechanism to learn from user interactions.

**Improvement**: Add:
- Query success/failure tracking
- "Was this helpful?" feedback collection
- Analytics on common query patterns to improve fuzzy matching thresholds
- A/B testing framework for prompt variations

### 9. Caching Layer

Repeated queries for the same transaction or merchant result in redundant processing.

**Improvement**: Add a caching layer for:
- Merchant lookups (merchants rarely change)
- Recent transaction queries (with short TTL)
- LLM responses for identical queries (with appropriate invalidation)

### 10. Proper Error Messages for Users

Currently, errors are logged but user-facing messages are generic.

**Improvement**: Create a structured error handling system that:
- Maps internal errors to user-friendly messages
- Provides actionable suggestions (e.g., "Try searching by amount instead")
- Maintains security by not exposing internal details
