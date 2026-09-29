from typing import Protocol

import cv2
import numpy as np
from shapely.geometry import Polygon

from pitch_pipeline.config import DetectorConfig


class FieldDetector(Protocol):
    def detect(self, frame: np.ndarray) -> Polygon | None: ...


class WhiteLineDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config

    # This detector looks for white field lines, a different detector can be used for real-world video
    def detect(self, frame: np.ndarray) -> Polygon | None:
        threshold = self.config.white_threshold

        lower = np.array([threshold, threshold, threshold], dtype=np.uint8)
        upper = np.array([255, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(frame, lower, upper)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < self.config.min_area:
            return None

        perimeter = cv2.arcLength(largest, True)
        epsilon = self.config.approx_epsilon_ratio * perimeter
        approximated = cv2.approxPolyDP(largest, epsilon, True)

        points = approximated.reshape(-1, 2)
        if len(points) < 3:
            return None

        polygon = Polygon(points)
        if not polygon.is_valid or polygon.is_empty:
            return None

        return polygon
