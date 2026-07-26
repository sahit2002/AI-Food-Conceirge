import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Production settings and environment configurations for AI Food Concierge."""

    # Swiggy MCP
    swiggy_mcp_url: str = field(
        default_factory=lambda: os.getenv("SWIGGY_FOOD_MCP_URL", "https://mcp.swiggy.com/food")
    )
    swiggy_access_token: str = field(
        default_factory=lambda: os.getenv("SWIGGY_ACCESS_TOKEN", "")
    )

    # LLM providers
    llm_provider: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER")  # explicit override only
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:latest")
    )

    gemini_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("ANTIGRAVITY_API_KEY")
    )
    anthropic_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY")
    )
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )

    # Model overrides
    llm_model: Optional[str] = field(
        default_factory=lambda: os.getenv("LLM_MODEL")
    )

    # Agent loop
    agent_max_turns: int = field(
        default_factory=lambda: int(os.getenv("AGENT_MAX_TURNS", "6"))
    )

    # MCP HTTP client
    mcp_request_timeout: int = field(
        default_factory=lambda: int(os.getenv("MCP_REQUEST_TIMEOUT", "30"))
    )
    mcp_max_retries: int = field(
        default_factory=lambda: int(os.getenv("MCP_MAX_RETRIES", "4"))
    )

    # Business rules
    cart_max_cap_inr: float = field(
        default_factory=lambda: float(os.getenv("CART_MAX_CAP_INR", "1000.0"))
    )
    default_address_label: str = field(
        default_factory=lambda: os.getenv("DEFAULT_ADDRESS_LABEL", "Home")
    )

    def validate(self) -> None:
        """Raise ValueError for any missing required secrets."""
        if not self.swiggy_access_token:
            raise ValueError(
                "SWIGGY_ACCESS_TOKEN is missing. Run 'python scripts/auth.py' to complete OAuth."
            )

    @property
    def active_llm_provider(self) -> str:
        """
        Return the active LLM provider.
        Priority:
          1. Explicit LLM_PROVIDER env var (if set and key exists)
          2. Auto-detect: first available cloud key (gemini → anthropic → openai)
          3. Ollama local fallback (only if nothing else is available)
        """
        explicit = (self.llm_provider or "").lower().strip()

        # Honour explicit override when the corresponding key is present
        if explicit == "gemini" and self.gemini_api_key:
            return "gemini"
        if explicit == "anthropic" and self.anthropic_api_key:
            return "anthropic"
        if explicit == "openai" and self.openai_api_key:
            return "openai"
        if explicit in ("ollama", "local"):
            return "ollama"

        # Auto-detect: first available cloud provider
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"

        # Last resort: local Ollama
        return "ollama"


settings = Settings()
