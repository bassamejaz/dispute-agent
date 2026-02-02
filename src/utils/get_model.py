from typing import Literal
from langchain.chat_models import init_chat_model

def create_llm(
    provider: Literal["gemini", "groq"],
    api_key: str,
    model: str,
    temperature: float = 0.3,
):
    """Create an LLM instance based on provider using init_chat_model.

    Args:
        provider: The LLM provider ('gemini' or 'groq')
        api_key: API key for the provider
        model: Model name to use
        temperature: Temperature for response generation

    Returns:
        Configured LLM instance
    """
    # Map our provider names to langchain model_provider names
    provider_map = {
        "gemini": "google_genai",
        "groq": "groq",
    }

    # Map API key environment variable names
    api_key_map = {
        "gemini": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
    }

    import os
    # Set the API key in environment for init_chat_model
    os.environ[api_key_map[provider]] = api_key

    return init_chat_model(
        model=model,
        model_provider=provider_map[provider],
        temperature=temperature,
    )
