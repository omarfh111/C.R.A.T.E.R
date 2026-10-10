"""Token/environment configuration. Never log token values."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import math

DEFAULT_MODEL="Qwen/Qwen3-VL-30B-A3B-Instruct"
DEFAULT_PROVIDER="deepinfra"

@dataclass(frozen=True)
class HFConfig:
    token: str = field(repr=False)
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    timeout_s: float = 45.
    max_side: int = 960
    max_tokens: int = 768
    max_requests: int = 100

    def __post_init__(self):
        if not self.token.startswith("hf_") or len(self.token)<10:
            raise ValueError("HF_TOKEN is missing or invalid; add your fine-grained token to .env")
        if not self.model or ":" in self.model or "/" not in self.model:
            raise ValueError("HF_MODEL must be an org/model ID without a provider suffix")
        if not self.provider or not all(c.isalnum() or c=="-" for c in self.provider):
            raise ValueError("invalid HF_PROVIDER")
        if not math.isfinite(self.timeout_s) or not 1<=self.timeout_s<=120:
            raise ValueError("HF_TIMEOUT_SECONDS must be between 1 and 120")
        if type(self.max_side) is not int or not 128<=self.max_side<=2048:
            raise ValueError("HF_MAX_SIDE must be between 128 and 2048")
        if type(self.max_tokens) is not int or not 128<=self.max_tokens<=2048:
            raise ValueError("HF_MAX_TOKENS must be between 128 and 2048")
        if type(self.max_requests) is not int or not 1<=self.max_requests<=1000:
            raise ValueError("HF_MAX_REQUESTS must be between 1 and 1000")

    @classmethod
    def load(cls,env_file=".env"):
        from dotenv import dotenv_values
        # Process environment takes precedence; parsing does not mutate os.environ.
        file_values=dotenv_values(env_file,interpolate=False) if Path(env_file).exists() else {}
        def value(name,default): return os.environ.get(name,file_values.get(name,default))
        return cls(token=value("HF_TOKEN","") or "",model=value("HF_MODEL",DEFAULT_MODEL),
            provider=value("HF_PROVIDER",DEFAULT_PROVIDER),timeout_s=float(value("HF_TIMEOUT_SECONDS","45")),
            max_side=int(value("HF_MAX_SIDE","960")),max_tokens=int(value("HF_MAX_TOKENS","768")),
            max_requests=int(value("HF_MAX_REQUESTS","100")))
