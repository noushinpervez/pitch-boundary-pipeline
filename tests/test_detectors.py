import cv2
import numpy as np

from pitch_pipeline.config import DetectorConfig
from pitch_pipeline.detectors import WhiteLineDetector


def test_detects_large_white_quadrilateral():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    image[:] = (0, 128, 0)

    points = np.array(
        [[70, 50], [250, 60], [270, 190], [55, 180]],
        dtype=np.int32,
    )
    cv2.polylines(
        image,
        [points],
        isClosed=True,
        color=(255, 255, 255),
        thickness=4,
    )

    detector = WhiteLineDetector(DetectorConfig())

    polygon = detector.detect(image)

    assert polygon is not None
    assert polygon.is_valid

    min_x, min_y, max_x, max_y = polygon.bounds
    assert min_x > 0
    assert min_y > 0
    assert max_x < image.shape[1] - 1
    assert max_y < image.shape[0] - 1


def test_returns_none_for_plain_green_image():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    image[:] = (0, 128, 0)

    detector = WhiteLineDetector(DetectorConfig())

    assert detector.detect(image) is None


def test_rejects_small_white_rectangle():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    image[:] = (0, 128, 0)

    cv2.rectangle(
        image,
        (100, 100),
        (109, 109),
        color=(255, 255, 255),
        thickness=-1,
    )

    detector = WhiteLineDetector(DetectorConfig(min_area=200.0))

    assert detector.detect(image) is None
