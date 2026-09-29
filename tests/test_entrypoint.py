import sys
from unittest.mock import Mock

import run_pipeline
from pitch_pipeline.config import AppConfig
from pitch_pipeline.processing import (
    Detection,
    ProcessingProgress,
    ProcessingResult,
    VideoOpenError,
)
from pitch_pipeline.reporting import ReportingError


def make_config() -> AppConfig:
    return AppConfig(video_path="video.mp4")


def make_result() -> ProcessingResult:
    polygon = Mock()
    polygon.exterior.coords = [
        (10.0, 10.0),
        (100.0, 10.0),
        (100.0, 100.0),
        (10.0, 10.0),
    ]

    representative = Detection(
        frame_index=0,
        polygon=polygon,
        clipped_area=8100.0,
    )

    return ProcessingResult(
        total_frames=25,
        sampled_frames=25,
        decoded_frames=25,
        decode_failures=0,
        valid_detections=25,
        invalid_detections=0,
        width=320,
        height=240,
        representative=representative,
        elapsed_seconds=0.5,
    )


def test_pipeline_failure_reports_failure_event_and_returns_2(monkeypatch):
    config = make_config()
    reporting_client = Mock()
    processor = Mock()
    processor.process.side_effect = VideoOpenError("could not open video")

    monkeypatch.setattr(run_pipeline, "load_config", Mock(return_value=config))
    monkeypatch.setattr(
        run_pipeline,
        "ReportingClient",
        Mock(return_value=reporting_client),
    )
    monkeypatch.setattr(
        run_pipeline,
        "VideoProcessor",
        Mock(return_value=processor),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pipeline.py", "--config", "config.json"],
    )

    result = run_pipeline.main()

    assert result == 2
    reporting_client.report_event.assert_called_once()

    failure_payload = reporting_client.report_event.call_args.args[0]
    assert failure_payload.event_type == "pipeline_failed"
    assert failure_payload.error_type == "VideoOpenError"
    assert failure_payload.message == "could not open video"


def test_completion_reporting_failure_returns_3(monkeypatch):
    config = make_config()
    reporting_client = Mock()
    reporting_client.report_event.side_effect = ReportingError("reporting unavailable")

    processor = Mock()
    processor.process.return_value = make_result()

    monkeypatch.setattr(run_pipeline, "load_config", Mock(return_value=config))
    monkeypatch.setattr(
        run_pipeline,
        "ReportingClient",
        Mock(return_value=reporting_client),
    )
    monkeypatch.setattr(
        run_pipeline,
        "VideoProcessor",
        Mock(return_value=processor),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pipeline.py", "--config", "config.json"],
    )

    result = run_pipeline.main()

    assert result == 3
    processor.process.assert_called_once()
    reporting_client.report_event.assert_called_once()


def test_progress_reporting_failure_does_not_stop_processing(monkeypatch):
    config = make_config()
    reporting_client = Mock()
    reporting_client.report_progress.side_effect = ReportingError(
        "progress reporting unavailable"
    )

    def make_processor(*args, **kwargs):
        processor = Mock()

        def process(_video_path):
            progress = ProcessingProgress(
                processed_samples=1,
                total_samples=25,
                valid_detections=1,
                invalid_detections=0,
                decode_failures=0,
            )
            kwargs["on_progress"](progress)
            return make_result()

        processor.process.side_effect = process
        return processor

    monkeypatch.setattr(run_pipeline, "load_config", Mock(return_value=config))
    monkeypatch.setattr(
        run_pipeline,
        "ReportingClient",
        Mock(return_value=reporting_client),
    )
    monkeypatch.setattr(
        run_pipeline,
        "VideoProcessor",
        Mock(side_effect=make_processor),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pipeline.py", "--config", "config.json"],
    )

    result = run_pipeline.main()

    assert result == 3
    reporting_client.report_progress.assert_called_once()
    reporting_client.report_event.assert_called_once()
