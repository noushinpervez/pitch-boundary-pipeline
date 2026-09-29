from unittest.mock import Mock

import pytest
import requests
from pydantic import ValidationError

from pitch_pipeline.config import ReportingConfig
from pitch_pipeline.reporting import (
    CompletionEventPayload,
    ProgressPayload,
    ReportingClient,
    ReportingError,
)


def test_inconsistent_progress_payload_counters_raise_validation_error():
    with pytest.raises(ValidationError):
        ProgressPayload(
            job_id="demo-job",
            processed_samples=3,
            total_samples=5,
            valid_detections=1,
            invalid_detections=1,
            decode_failures=0,
        )


def test_successful_progress_posts_once_with_timeout():
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "received"}
    session.post.return_value = response

    config = ReportingConfig(
        base_url="http://mock_api:5000",
        timeout_seconds=4.0,
        backoff_seconds=0,
    )
    client = ReportingClient(config, session=session)

    payload = ProgressPayload(
        job_id="demo-job",
        processed_samples=2,
        total_samples=5,
        valid_detections=1,
        invalid_detections=1,
        decode_failures=0,
    )

    client.report_progress(payload)

    session.post.assert_called_once_with(
        "http://mock_api:5000/api/v1/jobs/progress",
        json=payload.model_dump(mode="json"),
        timeout=4.0,
    )


def test_connection_error_retries_with_stable_event_id():
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"status": "received"}

    session.post.side_effect = [
        requests.exceptions.ConnectionError("connection failed"),
        response,
    ]

    sleep = Mock()
    config = ReportingConfig(
        base_url="http://mock_api:5000",
        max_attempts=3,
        backoff_seconds=0,
    )
    client = ReportingClient(config, session=session, sleep=sleep)

    payload = CompletionEventPayload(
        job_id="demo-job",
        sampled_frames=2,
        valid_detections=1,
        invalid_detections=1,
        decode_failures=0,
        representative_frame_index=0,
        representative_boundary=[
            (10.0, 10.0),
            (100.0, 10.0),
            (100.0, 100.0),
        ],
        representative_area=4050.0,
        elapsed_seconds=1.5,
    )

    event_id = payload.event_id

    client.report_event(payload)

    assert session.post.call_count == 2
    sleep.assert_called_once_with(0)

    first_payload = session.post.call_args_list[0].kwargs["json"]
    second_payload = session.post.call_args_list[1].kwargs["json"]

    assert first_payload["event_id"] == str(event_id)
    assert second_payload["event_id"] == str(event_id)
    assert first_payload["event_id"] == second_payload["event_id"]


def test_http_400_does_not_retry():
    session = Mock()
    response = Mock()
    response.status_code = 400
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=response
    )
    session.post.return_value = response

    sleep = Mock()
    config = ReportingConfig(
        base_url="http://mock_api:5000",
        max_attempts=5,
        backoff_seconds=0,
    )
    client = ReportingClient(config, session=session, sleep=sleep)

    payload = ProgressPayload(
        job_id="demo-job",
        processed_samples=1,
        total_samples=1,
        valid_detections=1,
        invalid_detections=0,
        decode_failures=0,
    )

    with pytest.raises(ReportingError):
        client.report_progress(payload)

    session.post.assert_called_once()
    sleep.assert_not_called()


def test_repeated_http_500_stops_at_max_attempts():
    session = Mock()
    response = Mock()
    response.status_code = 500
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=response
    )
    session.post.return_value = response

    sleep = Mock()
    config = ReportingConfig(
        base_url="http://mock_api:5000",
        max_attempts=3,
        backoff_seconds=0,
    )
    client = ReportingClient(config, session=session, sleep=sleep)

    payload = ProgressPayload(
        job_id="demo-job",
        processed_samples=1,
        total_samples=1,
        valid_detections=1,
        invalid_detections=0,
        decode_failures=0,
    )

    with pytest.raises(ReportingError):
        client.report_progress(payload)

    assert session.post.call_count == 3
    assert sleep.call_count == 2
    sleep.assert_called_with(0)
