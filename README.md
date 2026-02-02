# Transaction Dispute Resolution Agent

A GenAI-powered agent that helps users understand and dispute financial transactions using natural language queries.

## Features

- **Natural Language Understanding**: Ask questions like "I don't recognize this $50 charge from Coffee Palace last Tuesday"
- **Fuzzy Matching**: Handles approximate amounts and dates with configurable tolerance
- **Merchant Lookup**: Matches merchant names and aliases (e.g., "Amazon" matches "AMZN MKTP")
- **Dispute Filing**: Flag transactions for human review with conversation context
- **Security**: Input sanitization, prompt injection detection, PII masking in logs
- **Provider Flexibility**: Supports multiple LLM providers (Groq, Gemini) via abstraction

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Groq API key (default) or Google Gemini API key

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd glia-agent-v2

# Install dependencies
uv sync

# Create .env file with your API key
# For Groq (default):
echo "GROQ_API_KEY=your_api_key_here" > .env

# Or for Gemini:
echo "GEMINI_API_KEY=your_api_key_here" > .env
echo "LLM_PROVIDER=gemini" >> .env
```

### Running the Agent

```bash
# Start with default provider (Groq)
uv run python main.py

# Use Gemini instead
uv run python main.py --provider gemini

# With a specific user ID
uv run python main.py --user user_002

# Reset mock data
uv run python main.py --reset
```

## Usage

Once running, you can ask questions like:

- "I don't recognize this $50 charge from Coffee Palace"
- "Why did I just get charged $15?"
- "What's this Amazon charge for?"
- "I was charged twice by Netflix"
- "I want to dispute transaction txn_001"

### CLI Commands

| Command     | Description                    |
|-------------|--------------------------------|
| `/help`     | Show available commands        |
| `/clear`    | Clear conversation history     |
| `/history`  | Show conversation history      |
| `/disputes` | List your disputes             |
| `/quit`     | Exit the agent                 |

## Configuration

Configure via environment variables or `.env` file:

| Variable                  | Default              | Description                          |
|---------------------------|----------------------|--------------------------------------|
| `LLM_PROVIDER`            | groq                 | LLM provider (groq or gemini)        |
| `GROQ_API_KEY`            | (required for groq)  | Groq API key                         |
| `GROQ_MODEL`              | openai/gpt-oss-120b  | Groq model to use                    |
| `GEMINI_API_KEY`          | (required for gemini)| Google Gemini API key                |
| `GEMINI_MODEL`            | gemini-1.5-flash     | Gemini model to use                  |
| `AMOUNT_TOLERANCE_PERCENT`| 10.0                 | % tolerance for amount matching      |
| `DATE_TOLERANCE_DAYS`     | 3                    | Days tolerance for date matching     |
| `SHOW_REASONING`          | true                 | Show agent reasoning in responses    |
| `RESPONSE_TONE`           | formal               | Response tone (formal/friendly)      |
| `DEFAULT_CURRENCY`        | USD                  | Default currency code                |
| `LOG_LEVEL`               | INFO                 | Logging level                        |

## Project Structure

```
glia-agent-v2/
├── src/
│   ├── agent/              # ReAct agent implementation
│   │   ├── core.py         # Main agent logic
│   │   ├── prompts.py      # System prompts
│   │   ├── security.py     # Input sanitization
│   │   └── middleware/     # PII detection middleware
│   ├── tools/              # LangChain tools
│   │   ├── transactions.py
│   │   ├── merchants.py
│   │   ├── disputes.py
│   │   └── parsers.py
│   ├── models/             # Pydantic data models
│   ├── data/               # Mock data and storage
│   ├── utils/              # Logging, PII, resilience
│   └── config.py           # Configuration
├── data/                   # JSON data files
├── docs/                   # Documentation
│   ├── DESIGN_RATIONALE.md # Technical decision rationale
│   └── ARCHITECTURE_DECISIONS.md
├── tests/                  # Unit tests
├── main.py                 # CLI entry point
└── pyproject.toml
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Run specific test file
uv run pytest tests/test_parsers.py
```

## Mock Data

The agent includes 30 mock transactions covering various scenarios:

- Exact matches
- Fuzzy amount matches ($48.50 when user says $50)
- Fuzzy date matches (Wednesday when user says Tuesday)
- Multiple matching transactions
- Merchant aliases (AMZN MKTP for Amazon)
- Subscriptions (Netflix, Spotify)
- International transactions (EUR, GBP)
- Refunds and pending transactions

To reset data to defaults:

```bash
uv run python main.py --reset
```

## Security Features

- **Input Sanitization**: Removes dangerous characters, detects prompt injection patterns
- **PII Masking**: Two-layer approach - custom masking before agent + middleware for tool outputs
- **Audit Logging**: All interactions logged with PII redaction
- **User Isolation**: Users can only access their own transactions via session context
- **Prompt Hardening**: System prompt includes explicit security instructions

## Architecture

The agent uses the ReAct (Reasoning + Acting) pattern with LangChain v1:

1. User sends natural language query
2. Input is sanitized and PII is masked
3. Agent reasons about what information to extract
4. Agent calls appropriate tools (get_transactions, get_merchant_info, etc.)
5. Middleware redacts any PII in tool responses
6. Agent synthesizes results into a helpful response
7. User can request to dispute if needed

### Key Design Decisions

See [docs/DESIGN_RATIONALE.md](docs/DESIGN_RATIONALE.md) for detailed explanations of:
- Why LangChain over LangGraph/CrewAI/AutoGen
- Two-layer PII masking strategy
- Session-based user context
- Fuzzy matching with configurable thresholds
- And more...

## License

MIT
