import time
from collections.abc import Callable
from typing import Literal
from uuid import UUID, uuid4

import requests
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from pitch_pipeline.config import JobId, ReportingConfig
from pitch_pipeline.processing import ProcessingProgress, ProcessingResult


class ProgressPayload(BaseModel):
    """Client-side schema; the mock API does not enforce this schema."""

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    job_id: JobId
    status: Literal["running"] = "running"
    processed_samples: int = Field(ge=0)
    total_samples: int = Field(gt=0)
    valid_detections: int = Field(ge=0)
    invalid_detections: int = Field(ge=0)
    decode_failures: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counters(self) -> "ProgressPayload":
        if self.processed_samples > self.total_samples:
            raise ValueError("processed_samples cannot exceed total_samples")

        if (
            self.valid_detections + self.invalid_detections + self.decode_failures
            != self.processed_samples
        ):
            raise ValueError(
                "Detection and decode counters must equal processed_samples"
            )

        return self


class CompletionEventPayload(BaseModel):
    """Client-side schema; the mock API does not enforce this schema."""

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    job_id: JobId
    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["completed"] = "completed"
    sampled_frames: int = Field(gt=0)
    valid_detections: int = Field(gt=0)
    invalid_detections: int = Field(ge=0)
    decode_failures: int = Field(ge=0)
    representative_frame_index: int = Field(ge=0)
    representative_boundary: list[tuple[float, float]] = Field(min_length=3)
    representative_area: float = Field(gt=0)
    elapsed_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_counters(self) -> "CompletionEventPayload":
        if (
            self.valid_detections + self.invalid_detections + self.decode_failures
            != self.sampled_frames
        ):
            raise ValueError("Detection and decode counters must equal sampled_frames")

        return self


class FailureEventPayload(BaseModel):
    """Client-side schema; the mock API does not enforce this schema."""

    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )

    job_id: JobId
    event_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["pipeline_failed"] = "pipeline_failed"
    error_type: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class ReportingError(RuntimeError):
    pass


class ReportingClient:
    def __init__(
        self,
        config: ReportingConfig,
        session: requests.Session | None = None,
        logger=None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.session = session or requests.Session()
        self.logger = logger
        self.sleep = sleep

    def report_progress(self, payload: ProgressPayload) -> None:
        self._post("/api/v1/jobs/progress", payload)

    def report_event(
        self,
        payload: CompletionEventPayload | FailureEventPayload,
    ) -> None:
        self._post("/api/v1/jobs/events", payload)

    def _post(self, path: str, payload: BaseModel) -> None:
        url = f"{str(self.config.base_url).rstrip('/')}{path}"
        data = payload.model_dump(mode="json")
        last_failure: Exception | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = self.session.post(
                    url,
                    json=data,
                    timeout=self.config.timeout_seconds,
                )

                if response.status_code >= 500:
                    response.raise_for_status()

                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                if response.status_code != 200:
                    raise ReportingError(
                        f"Reporting API returned unexpected HTTP status "
                        f"{response.status_code}"
                    )

                try:
                    acknowledgement = response.json()
                except ValueError as exc:
                    raise ReportingError("Reporting API returned invalid JSON") from exc

                if not isinstance(acknowledgement, dict):
                    raise ReportingError(
                        "Reporting API returned an unexpected acknowledgement"
                    )

                if acknowledgement.get("status") != "received":
                    raise ReportingError(
                        "Reporting API returned an unexpected acknowledgement"
                    )

                return

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as exc:
                last_failure = exc

            except requests.exceptions.HTTPError as exc:
                last_failure = exc
                status_code = (
                    exc.response.status_code if exc.response is not None else None
                )

                if status_code is None or status_code < 500:
                    raise ReportingError("Reporting API request failed") from exc

            except ReportingError:
                raise

            except requests.exceptions.RequestException as exc:
                raise ReportingError("Reporting API request failed") from exc

            if attempt < self.config.max_attempts:
                self.sleep(self.config.backoff_seconds)

        raise ReportingError(
            "Reporting API request failed after " f"{self.config.max_attempts} attempts"
        ) from last_failure


def progress_payload(
    job_id: str,
    progress: ProcessingProgress,
) -> ProgressPayload:
    return ProgressPayload(
        job_id=job_id,
        processed_samples=progress.processed_samples,
        total_samples=progress.total_samples,
        valid_detections=progress.valid_detections,
        invalid_detections=progress.invalid_detections,
        decode_failures=progress.decode_failures,
    )


def completion_payload(
    job_id: str,
    result: ProcessingResult,
) -> CompletionEventPayload:
    coordinates = [
        (float(x), float(y))
        for x, y in result.representative.polygon.exterior.coords[:-1]
    ]

    return CompletionEventPayload(
        job_id=job_id,
        sampled_frames=result.sampled_frames,
        valid_detections=result.valid_detections,
        invalid_detections=result.invalid_detections,
        decode_failures=result.decode_failures,
        representative_frame_index=result.representative.frame_index,
        representative_boundary=coordinates,
        representative_area=float(result.representative.clipped_area),
        elapsed_seconds=float(result.elapsed_seconds),
    )
