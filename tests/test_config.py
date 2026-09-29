import pytest
from pydantic import ValidationError

from pitch_pipeline.config import AppConfig


def test_app_config_uses_documented_defaults():
    config = AppConfig(video_path="video.mp4")

    assert config.sampling.max_samples == 120
    assert config.detector.type == "white_line"


def test_app_config_rejects_unknown_nested_key():
    with pytest.raises(ValidationError):
        AppConfig(
            video_path="video.mp4",
            detector={"min_are": 1000.0},
        )
