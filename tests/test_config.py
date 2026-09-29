from pathlib import Path

import pytest
from pydantic import ValidationError

from pitch_pipeline.config import (
    AppConfig,
    ConfigurationError,
    load_config,
)


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


@pytest.mark.parametrize(
    "config_data",
    [
        {"video_path": "video.mp4", "job_id": "   "},
        {
            "video_path": "video.mp4",
            "reporting": {"base_url": "not-a-url"},
        },
        {
            "video_path": "video.mp4",
            "reporting": {"timeout_seconds": 0},
        },
        {
            "video_path": "video.mp4",
            "reporting": {"unexpected": True},
        },
    ],
)
def test_app_config_rejects_invalid_reporting_inputs(config_data):
    with pytest.raises(ValidationError):
        AppConfig.model_validate(config_data)


def test_load_config_success(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"video_path": "video.mp4"}',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.video_path == Path("video.mp4")
    assert config.sampling.max_samples == 120
    assert config.detector.type == "white_line"


def test_load_config_rejects_unknown_top_level_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"video_path": "video.mp4", "unknown_key": true}',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(config_path)

    assert "unknown_key" in str(exc_info.value)


def test_load_config_rejects_missing_file(tmp_path):
    config_path = tmp_path / "missing.json"

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(config_path)

    assert "Could not read configuration file" in str(exc_info.value)
