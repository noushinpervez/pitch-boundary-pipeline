from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

JobId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


class DetectorConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    type: Literal["white_line"] = "white_line"
    min_area: float = Field(default=1000.0, gt=0)
    white_threshold: int = Field(default=200, ge=0, le=255)
    approx_epsilon_ratio: float = Field(default=0.02, gt=0, lt=1)


class SamplingConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    max_samples: int = Field(default=120, gt=0)


class ReportingConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    base_url: AnyHttpUrl = "http://mock_api:5000"
    timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_seconds: float = Field(default=0.2, ge=0, le=5)


class AppConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    video_path: Path
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    job_id: JobId = "demo-job"
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)


class ConfigurationError(RuntimeError):
    pass


def load_config(path: Path) -> AppConfig:
    try:
        config_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Could not read configuration file: {path}") from exc

    try:
        return AppConfig.model_validate_json(config_text)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration in {path}: {exc}") from exc
