from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["white_line"] = "white_line"
    min_area: float = Field(default=1000.0, gt=0)
    white_threshold: int = Field(default=200, ge=0, le=255)
    approx_epsilon_ratio: float = Field(default=0.02, gt=0, lt=1)


class SamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_samples: int = Field(default=120, gt=0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: Path
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
