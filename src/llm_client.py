"""
LLM Client - handles communication with Claude/other LLMs.

Supports multiple providers:
- Anthropic (Claude) - default
- OpenAI-compatible APIs (OpenAI, Ollama, vLLM, Together, Groq, etc.)

Provider selection priority:
1. Agent YAML config `provider` field (if set)
2. Environment variable `LLM_PROVIDER`
3. Default: "anthropic"
"""
import os
import json
from typing import Optional
from .models import AgentConfig


# Default provider if not specified
DEFAULT_PROVIDER = "anthropic"


class LLMClient:
    """Client for interacting with LLM APIs (Anthropic or OpenAI-compatible)."""

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
    ):
        """
        Initialize the LLM client.

        Args:
            anthropic_api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
            openai_api_key: OpenAI-compatible API key (or use OPENAI_API_KEY env var)
            openai_base_url: Base URL for OpenAI-compatible API (or use OPENAI_BASE_URL env var)
        """
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._openai_base_url = openai_base_url or os.getenv("OPENAI_BASE_URL")

        # Lazy-loaded clients
        self._anthropic_client = None
        self._openai_client = None

        # Determine global default provider
        self._default_provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).lower()

        # Validate that we have credentials for the default provider
        if self._default_provider == "anthropic" and not self._anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Set it as environment variable or pass to constructor, "
                "or set LLM_PROVIDER=openai to use OpenAI-compatible API."
            )
        elif self._default_provider == "openai" and not self._openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY not found. "
                "Set it as environment variable or pass to constructor."
            )

    def _get_anthropic_client(self):
        """Get or create the Anthropic client."""
        if self._anthropic_client is None:
            from anthropic import Anthropic
            if not self._anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            self._anthropic_client = Anthropic(api_key=self._anthropic_api_key)
        return self._anthropic_client

    def _get_openai_client(self, base_url: Optional[str] = None):
        """
        Get or create an OpenAI-compatible client.

        Args:
            base_url: Custom base URL (e.g., for Ollama). If None, uses default.
        """
        # Use custom base_url if provided, otherwise use configured/env value
        effective_base_url = base_url or self._openai_base_url

        # For custom base URLs, always create a new client
        if effective_base_url and effective_base_url != self._openai_base_url:
            from openai import OpenAI
            if not self._openai_api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            return OpenAI(api_key=self._openai_api_key, base_url=effective_base_url)

        # Use cached client for default configuration
        if self._openai_client is None:
            from openai import OpenAI
            if not self._openai_api_key:
                raise ValueError("OPENAI_API_KEY not configured")
            kwargs = {"api_key": self._openai_api_key}
            if effective_base_url:
                kwargs["base_url"] = effective_base_url
            self._openai_client = OpenAI(**kwargs)

        return self._openai_client

    def _resolve_provider(self, agent_config: AgentConfig) -> str:
        """
        Resolve which provider to use for this request.

        Priority:
        1. Agent config provider field
        2. Global default (from LLM_PROVIDER env var or "anthropic")
        """
        if agent_config.provider:
            return agent_config.provider.lower()
        return self._default_provider

    def _generate_anthropic(
        self,
        agent_config: AgentConfig,
        full_prompt: str,
    ) -> str:
        """Generate response using Anthropic API."""
        client = self._get_anthropic_client()

        message = client.messages.create(
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            system=agent_config.system_prompt,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )

        return message.content[0].text

    def _generate_openai(
        self,
        agent_config: AgentConfig,
        full_prompt: str,
    ) -> str:
        """Generate response using OpenAI-compatible API."""
        client = self._get_openai_client(base_url=agent_config.api_base_url)

        # Build messages with system prompt as first message
        messages = []
        if agent_config.system_prompt:
            messages.append({"role": "system", "content": agent_config.system_prompt})
        messages.append({"role": "user", "content": full_prompt})

        response = client.chat.completions.create(
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            temperature=agent_config.temperature,
            messages=messages,
        )

        return response.choices[0].message.content

    def generate(
        self,
        agent_config: AgentConfig,
        user_prompt: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Generate a response using the configured agent.

        Args:
            agent_config: The agent configuration to use
            user_prompt: The user's prompt/task
            context: Optional additional context (e.g., related code files)

        Returns:
            The generated response text
        """
        # Build the full prompt with context if provided
        full_prompt = user_prompt
        if context:
            full_prompt = f"""## Context
{context}

## Task
{user_prompt}"""

        # Route to appropriate provider
        provider = self._resolve_provider(agent_config)

        if provider == "anthropic":
            return self._generate_anthropic(agent_config, full_prompt)
        elif provider == "openai":
            return self._generate_openai(agent_config, full_prompt)
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'.")

    def review(
        self,
        reviewer_config: AgentConfig,
        artifact: str,
        original_task: str,
    ) -> dict:
        """
        Have a reviewer agent evaluate an artifact.

        Args:
            reviewer_config: The reviewer agent configuration
            artifact: The generated artifact to review
            original_task: The original task description

        Returns:
            Dict with: passed, score, feedback, issues, suggestions
        """
        review_prompt = f"""## Original Task
{original_task}

## Artifact to Review
```
{artifact}
```

## Your Task
Review this artifact against the original task requirements.

Respond in the following JSON format:
{{
    "passed": true/false,
    "score": 0.0-1.0,
    "feedback": "Overall assessment",
    "issues": ["list", "of", "issues"],
    "suggestions": ["list", "of", "improvements"]
}}
"""

        response = self.generate(reviewer_config, review_prompt)

        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError:
            pass

        # Fallback if parsing fails
        return {
            "passed": False,
            "score": 0.5,
            "feedback": response,
            "issues": ["Could not parse structured review"],
            "suggestions": [],
        }
