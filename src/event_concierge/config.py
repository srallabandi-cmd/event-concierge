"""Configuration loading for goals, profile, and runtime settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"


class GoalSignals(BaseModel):
    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    id: str
    name: str
    weight: float
    signals: GoalSignals


class Thresholds(BaseModel):
    accept: float = 0.65
    review: float = 0.45
    decline: float = 0.45


class GoalsConfig(BaseModel):
    identity: dict[str, str] = Field(default_factory=dict)
    goals: list[Goal] = Field(default_factory=list)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    event_types: dict[str, list[str]] = Field(default_factory=dict)


class PersonalProfile(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    linkedin_url: str = ""
    title: str = ""
    company: str = ""
    location: str = "San Francisco, CA"
    bio: str = ""


class ProfileConfig(BaseModel):
    personal: PersonalProfile
    preferences: dict[str, str] = Field(default_factory=dict)
    reply_templates: dict[str, str] = Field(default_factory=dict)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cursor_api_key: str = Field(default="", alias="CURSOR_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    gmail_credentials_path: Path = Field(
        default=Path.home() / ".config/event-concierge/gmail_credentials.json",
        alias="GMAIL_CREDENTIALS_PATH",
    )
    gmail_token_path: Path = Field(
        default=Path.home() / ".config/event-concierge/gmail_token.json",
        alias="GMAIL_TOKEN_PATH",
    )

    linkedin_profile_dir: Path = Field(
        default=Path.home() / ".config/event-concierge/linkedin_profile",
        alias="LINKEDIN_PROFILE_DIR",
    )

    notify_email: str = Field(default="", alias="NOTIFY_EMAIL")
    notify_phone: str = Field(default="", alias="NOTIFY_PHONE")

    user_full_name: str = Field(default="", alias="USER_FULL_NAME")
    user_email: str = Field(default="", alias="USER_EMAIL")
    user_linkedin_url: str = Field(default="", alias="USER_LINKEDIN_URL")
    user_title: str = Field(default="", alias="USER_TITLE")
    user_company: str = Field(default="", alias="USER_COMPANY")
    user_location: str = Field(default="San Francisco, CA", alias="USER_LOCATION")

    data_dir: Path = DATA_DIR
    config_dir: Path = CONFIG_DIR

    def expand_paths(self) -> Settings:
        self.gmail_credentials_path = Path(
            os.path.expanduser(str(self.gmail_credentials_path))
        )
        self.gmail_token_path = Path(os.path.expanduser(str(self.gmail_token_path)))
        self.linkedin_profile_dir = Path(os.path.expanduser(str(self.linkedin_profile_dir)))
        return self


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f) or {}


@lru_cache
def get_settings() -> Settings:
    return Settings().expand_paths()


@lru_cache
def get_goals_config() -> GoalsConfig:
    path = CONFIG_DIR / "goals.yaml"
    return GoalsConfig.model_validate(_load_yaml(path))


@lru_cache
def get_profile_config() -> ProfileConfig:
    path = CONFIG_DIR / "profile.yaml"
    return ProfileConfig.model_validate(_load_yaml(path))


def ensure_data_dirs() -> None:
    for sub in ("processed", "sessions", "briefings", "state"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)


def ensure_config_dirs() -> None:
    settings = get_settings()
    settings.linkedin_profile_dir.mkdir(parents=True, exist_ok=True)
    settings.gmail_token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.gmail_credentials_path.parent.mkdir(parents=True, exist_ok=True)
