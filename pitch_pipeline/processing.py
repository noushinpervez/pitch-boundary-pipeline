import logging
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import cv2
from shapely.geometry import Polygon, box

from pitch_pipeline.detectors import FieldDetector
from pitch_pipeline.sampling import uniform_frame_indices


@dataclass(frozen=True)
class Detection:
    frame_index: int
    polygon: Polygon
    clipped_area: float


class VideoProcessingError(RuntimeError):
    pass


class VideoOpenError(VideoProcessingError):
    pass


class InvalidVideoMetadataError(VideoProcessingError):
    pass


class NoValidDetectionsError(VideoProcessingError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    total_frames: int
    sampled_frames: int
    decoded_frames: int
    decode_failures: int
    valid_detections: int
    invalid_detections: int
    width: int
    height: int
    representative: Detection
    elapsed_seconds: float


def select_representative_detection(
    detections: list[Detection],
) -> Detection:
    if not detections:
        raise ValueError("detections must not be empty")

    median_area = median(detection.clipped_area for detection in detections)

    # Use one real detected polygon instead of combining different detections
    return min(
        detections,
        key=lambda detection: abs(detection.clipped_area - median_area),
    )


class VideoProcessor:
    def __init__(
        self,
        detector: FieldDetector,
        max_samples: int,
        logger: logging.Logger | None = None,
    ):
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")

        self.detector = detector
        self.max_samples = max_samples
        self.logger = logger or logging.getLogger(__name__)

    def process(self, video_path: Path) -> ProcessingResult:
        start_time = time.perf_counter()
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            cap.release()
            raise VideoOpenError(f"Could not open video: {video_path}")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            if total_frames <= 0 or width <= 1 or height <= 1:
                raise InvalidVideoMetadataError(
                    f"Invalid video metadata: frames={total_frames}, "
                    f"width={width}, height={height}"
                )

            indices = uniform_frame_indices(total_frames, self.max_samples)
            boundary = box(0, 0, width - 1, height - 1)

            decoded_frames = 0
            decode_failures = 0
            valid_detections = 0
            invalid_detections = 0
            detections: list[Detection] = []

            for frame_index in indices:
                if not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                    decode_failures += 1
                    self.logger.warning("Failed to seek to frame %d", frame_index)
                    continue

                success, frame = cap.read()
                if not success or frame is None:
                    decode_failures += 1
                    self.logger.warning("Failed to read frame %d", frame_index)
                    continue

                decoded_frames += 1
                polygon = self.detector.detect(frame)

                if (
                    polygon is None
                    or polygon.is_empty
                    or not polygon.is_valid
                    or not isinstance(polygon, Polygon)
                ):
                    invalid_detections += 1
                    continue

                clipped = polygon.intersection(boundary)

                if (
                    not isinstance(clipped, Polygon)
                    or clipped.is_empty
                    or not clipped.is_valid
                    or clipped.area <= 0
                ):
                    invalid_detections += 1
                    continue

                valid_detections += 1
                detections.append(
                    Detection(
                        frame_index=frame_index,
                        polygon=clipped,
                        clipped_area=clipped.area,
                    )
                )

            if not detections:
                raise NoValidDetectionsError("No valid field detections found")

            representative = select_representative_detection(detections)

            return ProcessingResult(
                total_frames=total_frames,
                sampled_frames=len(indices),
                decoded_frames=decoded_frames,
                decode_failures=decode_failures,
                valid_detections=valid_detections,
                invalid_detections=invalid_detections,
                width=width,
                height=height,
                representative=representative,
                elapsed_seconds=time.perf_counter() - start_time,
            )
        finally:
            cap.release()
