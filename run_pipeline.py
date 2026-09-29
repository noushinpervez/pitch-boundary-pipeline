import argparse
import logging
import os
from pathlib import Path

from pitch_pipeline.config import ConfigurationError, load_config
from pitch_pipeline.detectors import WhiteLineDetector
from pitch_pipeline.processing import ProcessingProgress, VideoProcessor
from pitch_pipeline.reporting import (
    FailureEventPayload,
    ReportingClient,
    ReportingError,
    completion_payload,
    progress_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the pitch-processing pipeline.")
    parser.add_argument(
        "--config",
        help="Path to the JSON configuration file.",
    )

    args = parser.parse_args()

    config_value = args.config or os.environ.get("PIPELINE_CONFIG")

    if not config_value:
        parser.error("--config or PIPELINE_CONFIG must specify a configuration file")

    config_path = Path(config_value)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logger = logging.getLogger(__name__)

    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        logger.error("%s", exc)
        return 1

    video_path = config.video_path
    if not video_path.is_absolute():
        video_path = config_path.parent / video_path

    reporting_client = ReportingClient(
        config.reporting,
        logger=logger,
    )
    detector = WhiteLineDetector(config.detector)

    reporting_degraded = False

    def on_progress(progress: ProcessingProgress) -> None:
        nonlocal reporting_degraded

        if reporting_degraded:
            return

        try:
            reporting_client.report_progress(progress_payload(config.job_id, progress))
        except ReportingError as exc:
            logger.error("Progress reporting failed: %s", exc)
            # Disable further progress reporting after a failure, terminal reporting still runs
            reporting_degraded = True

    processor = VideoProcessor(
        detector=detector,
        max_samples=config.sampling.max_samples,
        logger=logger,
        on_progress=on_progress,
    )

    try:
        result = processor.process(video_path)
    except Exception as exc:
        logger.exception("Pipeline processing failed")

        error_message = (str(exc) or repr(exc))[:500]

        failure_payload = FailureEventPayload(
            job_id=config.job_id,
            error_type=type(exc).__name__,
            message=error_message,
        )

        try:
            reporting_client.report_event(failure_payload)
        except ReportingError as reporting_exc:
            logger.error(
                "Failure-event reporting also failed: %s",
                reporting_exc,
            )

        return 2

    logger.info(
        "Processing complete: sampled=%d decoded=%d valid=%d "
        "invalid=%d decode_failures=%d elapsed=%.3fs",
        result.sampled_frames,
        result.decoded_frames,
        result.valid_detections,
        result.invalid_detections,
        result.decode_failures,
        result.elapsed_seconds,
    )

    completion_event = completion_payload(
        config.job_id,
        result,
    )

    try:
        reporting_client.report_event(completion_event)
    except ReportingError as exc:
        logger.error("Completion-event reporting failed: %s", exc)
        return 3

    if reporting_degraded:
        logger.error("Progress reporting was degraded during processing.")
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
