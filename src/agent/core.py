"""Core ReAct agent implementation using LangChain's create_agent."""

from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware

from langchain_core.messages import HumanMessage, AIMessage

from src.agent.middleware.detect_ssn import detect_ssn

from src.config import settings
from src.agent.prompts import get_system_prompt
from src.agent.security import sanitize_input, is_on_topic
from src.tools.transactions import get_transactions, get_transaction_by_id
from src.tools.merchants import get_merchant_info, search_merchant_by_name
from src.tools.disputes import flag_for_review, get_dispute_status, list_user_disputes
from src.data.storage import Storage
from src.utils.logging import AuditLogger, get_logger
from src.utils.resilience import with_retry, RateLimiter, CircuitBreaker
from src.utils.get_model import create_llm
from src.utils.pii import mask_pii


logger = get_logger("agent", settings.log_level)


class DisputeAgent:
    """ReAct agent for transaction dispute resolution."""

    def __init__(
        self,
        user_id: str,
        provider: Literal["gemini", "groq"] | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize the dispute agent.

        Args:
            user_id: The user ID for this session
            provider: LLM provider ('gemini' or 'groq'), uses settings if not provided
            api_key: Optional API key (uses settings if not provided)
            model: Optional model name (uses settings if not provided)
        """
        self.user_id = user_id
        self.provider = provider or settings.llm_provider

        # Determine API key and model based on provider
        if self.provider == "gemini":
            self.api_key = api_key or settings.gemini_api_key
            self.model_name = model or settings.gemini_model
        elif self.provider == "groq":
            self.api_key = api_key or settings.groq_api_key
            self.model_name = model or settings.groq_model
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        if not self.api_key:
            key_env = "GEMINI_API_KEY" if self.provider == "gemini" else "GROQ_API_KEY"
            raise ValueError(
                f"{self.provider.title()} API key is required. "
                f"Set {key_env} in .env or pass api_key parameter."
            )

        # Initialize components
        self.storage = Storage()
        self.audit_logger = AuditLogger(user_id=user_id)
        self.rate_limiter = RateLimiter(settings.rate_limit_rpm)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_threshold
        )

        # Initialize LLM using init_chat_model
        self.llm = create_llm(
            provider=self.provider,
            api_key=self.api_key,
            model=self.model_name,
            temperature=0.3,
        )

        # Define tools
        self.tools = [
            get_transactions,
            get_transaction_by_id,
            get_merchant_info,
            search_merchant_by_name,
            flag_for_review,
            get_dispute_status,
            list_user_disputes,
        ]

        # Create agent using LangChain's create_agent
        # This handles all tool calling automatically
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=get_system_prompt(settings.prompt_config.response_tone, settings.prompt_config.show_reasoning),
            middleware=[
                PIIMiddleware("email", strategy="redact", apply_to_input=False, apply_to_tool_results=True),
                PIIMiddleware(
                    "credit_card",
                    strategy="redact",
                    apply_to_input=False,
                    apply_to_tool_results=True,
                ),
                PIIMiddleware(
                    "ssn",
                    detector=detect_ssn,
                    strategy="redact",
                    apply_to_input=False,
                    apply_to_tool_results=True,
                ),
            ],
        )

        # Load conversation history
        self.messages: list = []
        self._load_session()

        logger.info(f"Initialized DisputeAgent with {self.provider}/{self.model_name}")
    
    def _load_session(self):
        """Load conversation history from storage."""
        history = self.storage.get_session(self.user_id)
        for msg in history:
            if msg["role"] == "user":
                self.messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                self.messages.append(AIMessage(content=msg["content"]))

    def _save_session(self):
        """Save conversation history to storage."""
        history = []
        for msg in self.messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
        self.storage.save_session(self.user_id, history)

    @with_retry(max_attempts=3, backoff_base=2.0)
    def _invoke_agent(self, messages: list) -> dict:
        """Invoke the agent with retry logic."""
        self.rate_limiter.acquire()
        return self.circuit_breaker.call(
            self.agent.invoke,
            {"messages": messages},
        )

    def process_message(self, user_input: str) -> str:
        """Process a user message and return the agent's response.

        Args:
            user_input: The user's message

        Returns:
            The agent's response string
        """
        # Sanitize input
        sanitized = sanitize_input(user_input, self.user_id)
        if sanitized.warnings:
            logger.warning(f"Input sanitization warnings: {sanitized.warnings}")

        # Log user input
        self.audit_logger.log_user_input(sanitized.text)
        masked_input = mask_pii(sanitized.text, use_presidio=True)


        # Add user message to history
        self.messages.append(HumanMessage(content=masked_input))

        try:
            # Invoke the agent with full message history
            result = self._invoke_agent(self.messages)

            # Extract the final response from the agent
            response_messages = result.get("messages", [])

            # Find the last AI message as the final response
            final_response = "I couldn't process your request."
            for msg in reversed(response_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    final_response = msg.content
                    break

            # Log response
            self.audit_logger.log_llm_response(
                response=final_response,
                model=self.model_name,
            )

            # Update message history with the actual user message (not the contextualized one)
            self.messages[-1] = HumanMessage(content=masked_input)
            self.messages.append(AIMessage(content=final_response))
            self._save_session()

            return final_response

        except Exception as e:
            logger.error(f"Error in agent execution: {e}")
            self.audit_logger.log_security_event(
                "agent_error",
                str(e),
                "error",
            )
            # Remove the failed message from history
            if self.messages and isinstance(self.messages[-1], HumanMessage):
                self.messages.pop()
            return (
                "I apologize, but I encountered an issue processing your request. "
                "Please try again, or if the problem persists, contact support."
            )

    def clear_history(self):
        """Clear conversation history."""
        self.messages = []
        self.storage.clear_session(self.user_id)

    def get_history(self) -> list[dict]:
        """Get conversation history.

        Returns:
            List of message dictionaries with 'role' and 'content'
        """
        history = []
        for msg in self.messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
        return history
