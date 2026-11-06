"""Environment-driven settings.

Loads the .env file (if present) before reading environment variables,
so any entrypoint (API, worker, CLI, tests) gets the same behavior.

Fails fast on missing critical variables. Never logs the private key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from relayer.domain.value_objects import Address, Amount, Policy
from relayer.infrastructure.composition import Config


# Load .env once, from the project root (parent of src/relayer/config).
# override=False: shell-exported vars win over .env values.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value.strip()


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


@dataclass(frozen=True)
class Settings:
    # Network
    rpc_url: str
    chain_id: int
    usdc_address: str
    usdc_name: str
    usdc_version: str
    token_decimals: int
    # Relayer
    relayer_private_key: str
    db_path: str
    # Policy
    max_value_per_tx_raw: int
    max_validity_window_seconds: int
    min_remaining_validity_seconds: int
    allowed_destinations: frozenset[str] | None
    # Execution
    confirmations_required: int
    # API
    api_host: str
    api_port: int
    log_level: str
    # Worker
    worker_enabled: bool
    worker_batch_size: int
    worker_poll_interval_seconds: float

    @classmethod
    def from_env(cls) -> Settings:
        allowed_raw = _optional("ALLOWED_DESTINATIONS", "")
        allowed = (
            frozenset(a.strip().lower() for a in allowed_raw.split(",") if a.strip())
            if allowed_raw
            else None
        )
        if allowed is not None:
            for addr in allowed:
                Address(addr)

        return cls(
            rpc_url=_require("RPC_URL"),
            chain_id=int(_require("CHAIN_ID")),
            usdc_address=_require("USDC_ADDRESS"),
            usdc_name=_require("USDC_NAME"),
            usdc_version=_require("USDC_VERSION"),
            token_decimals=int(_optional("TOKEN_DECIMALS", "6")),
            relayer_private_key=_require("RELAYER_PRIVATE_KEY"),
            db_path=_optional("DB_PATH", "relayer.db"),
            max_value_per_tx_raw=int(_require("MAX_VALUE_PER_TX_RAW")),
            max_validity_window_seconds=int(
                _optional("MAX_VALIDITY_WINDOW_SECONDS", "259200")
            ),
            min_remaining_validity_seconds=int(
                _optional("MIN_REMAINING_VALIDITY_SECONDS", "60")
            ),
            allowed_destinations=allowed,
            confirmations_required=int(_optional("CONFIRMATIONS_REQUIRED", "1")),
            api_host=_optional("API_HOST", "127.0.0.1"),
            api_port=int(_optional("API_PORT", "8000")),
            log_level=_optional("LOG_LEVEL", "INFO").upper(),
            worker_enabled=_optional("WORKER_ENABLED", "true").lower() == "true",
            worker_batch_size=int(_optional("WORKER_BATCH_SIZE", "10")),
            worker_poll_interval_seconds=float(
                _optional("WORKER_POLL_INTERVAL_SECONDS", "3.0")
            ),
        )

    def to_config(self) -> Config:
        policy = Policy(
            max_value=Amount(
                raw=self.max_value_per_tx_raw, decimals=self.token_decimals
            ),
            max_validity_window_seconds=self.max_validity_window_seconds,
            min_remaining_validity_seconds=self.min_remaining_validity_seconds,
            allowed_destinations=(
                frozenset(Address(a) for a in self.allowed_destinations)
                if self.allowed_destinations is not None
                else None
            ),
        )
        return Config(
            rpc_url=self.rpc_url,
            chain_id=self.chain_id,
            usdc_address=self.usdc_address,
            usdc_name=self.usdc_name,
            usdc_version=self.usdc_version,
            token_decimals=self.token_decimals,
            relayer_private_key=self.relayer_private_key,
            db_path=self.db_path,
            policy=policy,
            confirmations_required=self.confirmations_required,
        )

    def __repr__(self) -> str:
        return (
            f"Settings(chain_id={self.chain_id}, "
            f"usdc_address={self.usdc_address}, "
            f"db_path={self.db_path}, "
            f"api={self.api_host}:{self.api_port})"
        )
