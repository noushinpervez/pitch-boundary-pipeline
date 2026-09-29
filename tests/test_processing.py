from unittest.mock import Mock

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


def test_selects_detection_closest_to_median_area():
    polygon = box(0, 0, 1, 1)

    detections = [
        Detection(frame_index=1, polygon=polygon, clipped_area=100),
        Detection(frame_index=2, polygon=polygon, clipped_area=110),
        Detection(frame_index=3, polygon=polygon, clipped_area=500),
    ]

    selected = select_representative_detection(detections)

    assert selected.clipped_area == 110
    assert selected.frame_index == 2


def test_empty_detections_raise_value_error():
    with pytest.raises(ValueError):
        select_representative_detection([])


def test_video_open_failure_releases_capture(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = False

    monkeypatch.setattr(
        "pitch_pipeline.processing.cv2.VideoCapture",
        Mock(return_value=capture),
    )

    detector = Mock()
    processor = VideoProcessor(detector, max_samples=5)

    with pytest.raises(VideoOpenError):
        processor.process("video.mp4")

    capture.release.assert_called_once()


def test_no_valid_detections_releases_capture(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.side_effect = [1, 320, 240]
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
    processor = VideoProcessor(detector, max_samples=5)

    with pytest.raises(NoValidDetectionsError):
        processor.process("video.mp4")

    capture.release.assert_called_once()


def test_unexpected_detector_error_propagates_and_releases_capture(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.get.side_effect = [1, 320, 240]
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
    processor = VideoProcessor(detector, max_samples=5)

    with pytest.raises(RuntimeError, match="boom"):
        processor.process("video.mp4")

    capture.release.assert_called_once()
