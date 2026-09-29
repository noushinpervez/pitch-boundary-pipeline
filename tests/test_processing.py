from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from shapely.geometry import box

from pitch_pipeline.processing import (
    Detection,
    NoValidDetectionsError,
    VideoOpenError,
    VideoProcessor,
    select_representative_detection,
)


def test_select_representative_detection_uses_median_area():
    polygon = box(0, 0, 1, 1)

    detections = [
        Detection(frame_index=1, polygon=polygon, clipped_area=100),
        Detection(frame_index=2, polygon=polygon, clipped_area=110),
        Detection(frame_index=3, polygon=polygon, clipped_area=500),
    ]

    result = select_representative_detection(detections)

    assert result.frame_index == 2
    assert result.clipped_area == 110


def test_select_representative_detection_rejects_empty_list():
    with pytest.raises(ValueError):
        select_representative_detection([])


def test_video_processor_raises_video_open_error_and_releases_capture(
    monkeypatch,
):
    capture = Mock()
    capture.isOpened.return_value = False

    monkeypatch.setattr(
        "pitch_pipeline.processing.cv2.VideoCapture",
        Mock(return_value=capture),
    )

    processor = VideoProcessor(
        detector=Mock(),
        max_samples=1,
    )

    with pytest.raises(VideoOpenError):
        processor.process(Path("test.mp4"))

    capture.release.assert_called_once()


def test_video_processor_raises_no_valid_detections_and_releases_capture(
    monkeypatch,
):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_COUNT: 1,
        cv2.CAP_PROP_FRAME_WIDTH: 320,
        cv2.CAP_PROP_FRAME_HEIGHT: 240,
    }[prop]
    capture.set.return_value = True
    capture.read.return_value = (
        True,
        np.zeros((240, 320, 3), dtype=np.uint8),
    )

    monkeypatch.setattr(
        "pitch_pipeline.processing.cv2.VideoCapture",
        Mock(return_value=capture),
    )

    detector = Mock()
    detector.detect.return_value = None

    processor = VideoProcessor(
        detector=detector,
        max_samples=1,
    )

    with pytest.raises(NoValidDetectionsError):
        processor.process(Path("test.mp4"))

    capture.release.assert_called_once()


def test_video_processor_propagates_unexpected_detector_error_and_releases(
    monkeypatch,
):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_COUNT: 1,
        cv2.CAP_PROP_FRAME_WIDTH: 320,
        cv2.CAP_PROP_FRAME_HEIGHT: 240,
    }[prop]
    capture.set.return_value = True
    capture.read.return_value = (
        True,
        np.zeros((240, 320, 3), dtype=np.uint8),
    )

    monkeypatch.setattr(
        "pitch_pipeline.processing.cv2.VideoCapture",
        Mock(return_value=capture),
    )

    detector = Mock()
    detector.detect.side_effect = RuntimeError("boom")

    processor = VideoProcessor(
        detector=detector,
        max_samples=1,
    )

    with pytest.raises(RuntimeError, match="boom"):
        processor.process(Path("test.mp4"))

    capture.release.assert_called_once()


def test_processing_emits_startup_and_final_progress(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_COUNT: 25,
        cv2.CAP_PROP_FRAME_WIDTH: 320,
        cv2.CAP_PROP_FRAME_HEIGHT: 240,
    }[prop]
    capture.set.return_value = True
    capture.read.return_value = (
        True,
        np.zeros((240, 320, 3), dtype=np.uint8),
    )

    monkeypatch.setattr(
        "pitch_pipeline.processing.cv2.VideoCapture",
        Mock(return_value=capture),
    )

    detector = Mock()
    detector.detect.return_value = box(20, 20, 100, 100)

    on_progress = Mock()
    processor = VideoProcessor(
        detector=detector,
        max_samples=25,
        on_progress=on_progress,
    )

    processor.process(Path("test.mp4"))

    first_snapshot = on_progress.call_args_list[0].args[0]
    last_snapshot = on_progress.call_args_list[-1].args[0]

    assert first_snapshot.processed_samples == 0
    assert last_snapshot.processed_samples == 25
    assert (
        last_snapshot.valid_detections
        + last_snapshot.invalid_detections
        + last_snapshot.decode_failures
        == 25
    )
    capture.release.assert_called_once()
