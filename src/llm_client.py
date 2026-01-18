"""
LLM Client - handles communication with Claude/other LLMs.
"""
import os
from anthropic import Anthropic
from typing import Optional
from .models import AgentConfig


class LLMClient:
    """Client for interacting with LLM APIs."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. "
                "Set it as environment variable or pass to constructor."
            )
        self.client = Anthropic(api_key=self.api_key)
    
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

        message = self.client.messages.create(
            model=agent_config.model,
            max_tokens=agent_config.max_tokens,
            system=agent_config.system_prompt,
            messages=[
                {"role": "user", "content": full_prompt}
            ]
        )
        
        return message.content[0].text
    
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
        import json
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
