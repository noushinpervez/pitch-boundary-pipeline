# Pitch Pipeline

## Overview

This repository refactors the supplied research prototype into a tested batch pipeline. It processes finite video files using a fixed inspection budget, detects synthetic white pitch boundaries through a replaceable interface, validates all configuration with Pydantic and reports progress and terminal outcomes to the supplied mock API. The full workflow runs through Docker Compose.

Two limits apply to the current submission. The white-line detector is tuned to the synthetic feed and is not a production segmentation model. Crop-layout optimization is not implemented; the supplied README explicitly excludes it from scope.


## Architecture

`run_pipeline.py` is the entry point. It wires dependencies, configures logging and maps outcomes to exit codes. It does not contain business logic.

`pitch_pipeline/config.py` defines strict Pydantic models and loads the JSON config file. All validation runs here before any video is opened.

`pitch_pipeline/detectors.py` defines the `FieldDetector` protocol and provides the synthetic `WhiteLineDetector`. Processing depends on the protocol, not the concrete class. Any compliant detector can be swapped in.

`pitch_pipeline/sampling.py` selects uniformly distributed frame indices up to `max_samples`. It has no video I/O or detection logic.

`pitch_pipeline/processing.py` handles video I/O, frame validation, detection dispatch, polygon aggregation, cleanup and progress callbacks. It is the core library component.

`pitch_pipeline/reporting.py` builds validated payloads, manages the HTTP client, enforces timeouts, handles retries and checks acknowledgements.

`mock_api/` is the supplied service. It is unchanged.


## Repository layout

```text
pitch_pipeline/
    config.py          # Pydantic models, JSON loading, validation
    detectors.py       # FieldDetector protocol, WhiteLineDetector
    sampling.py        # Fixed-budget uniform frame selection
    processing.py      # Video I/O, aggregation, cleanup, progress
    reporting.py       # HTTP client, payloads, retries
tests/                 # pytest suite (33 checks)
run_pipeline.py        # Entry point, logging, exit codes
config.example.json    # Template for local runs
config.docker.json     # Config used by the Compose runner service
Dockerfile             # Runner image
docker-compose.yml     # Generator, runner and mock API services
synthetic_generator.py # Supplied video generator, unchanged
mock_api/              # Supplied Flask API, unchanged
DECISIONS.md           # Architecture rationale, assumptions, disclosure
```


## Docker Compose quick start

This is the primary reproducible execution path. Run these commands in order.

```powershell
docker compose up --build -d
docker compose ps -a
docker compose logs runner
Invoke-RestMethod 'http://localhost:5000/api/v1/jobs/events' | ConvertTo-Json -Depth 10
docker compose down
```

What each step does:

- `video_generator` writes input video into a named volume shared with the runner.
- `runner` waits for generation to finish and for the API health check to pass before starting.
- Both `video_generator` and `runner` exit with code `0` on success. Check this with `docker compose ps -a`.
- The mock API stays running until `docker compose down`.
- Inside Compose, the runner reaches the API at `http://mock_api:5000`.
- `docker compose down` without `--volumes` preserves the named volume. Add `--volumes` to remove it.


## Local setup and execution

These steps run the pipeline locally against the real mock API container.

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "from synthetic_generator import generate_synthetic_video; generate_synthetic_video('synthetic_pitch_feed.mp4')"
Copy-Item .\config.example.json .\config.local.json
docker compose up -d mock_api
python .\run_pipeline.py --config .\config.local.json
docker compose down
```

Before running, set this in `config.local.json`:

```json
"base_url": "http://localhost:5000"
```

The Compose runner uses `http://mock_api:5000` because it resolves the service name internally. The local runner uses `http://localhost:5000` because it runs on the host.

`--config` points to the JSON file directly. If it is omitted, the `PIPELINE_CONFIG` environment variable locates the same file. Either way, all configuration values live in the validated JSON file. There is no per-field environment variable parsing.


## Configuration

Unknown keys are rejected at every nesting level. Invalid explicit values never fall back to defaults.

| Field | Required | Default | Constraints |
|---|---|---|---|
| `video_path` | Yes | | Relative paths resolve from the config file's directory |
| `job_id` | No | `demo-job` | Trimmed, 1 to 100 characters |
| `detector.type` | No | `white_line` | Only `white_line` is accepted |
| `detector.min_area` | No | `1000.0` | Greater than `0` |
| `detector.white_threshold` | No | `200` | `0` to `255` |
| `detector.approx_epsilon_ratio` | No | `0.02` | Greater than `0`, less than `1` |
| `sampling.max_samples` | No | `120` | Greater than `0` |
| `reporting.base_url` | No | `http://mock_api:5000` | Valid HTTP/HTTPS URL |
| `reporting.timeout_seconds` | No | `2.0` | Greater than `0`, at most `30` |
| `reporting.max_attempts` | No | `3` | From `1` through `5` |
| `reporting.backoff_seconds` | No | `0.2` | From `0` through `5` |


## Detection, sampling and aggregation

The supplied synthetic feed encodes pitch boundaries as white markings. The detector thresholds those pixels, rejects small contours using `min_area` and simplifies the accepted contour into a polygon. No confidence value is produced or fabricated.

At most `max_samples` frame indices are selected, distributed uniformly across the file. The detector is called once per selected frame. Detections that are empty, geometrically invalid, or outside the frame boundary are counted and excluded.

The representative output is a real observed polygon, not an average of vertices. It is the valid detection whose area is closest to the median valid area across all samples. Averaging vertices across different camera views would produce a shape that matches none of them.

Multiple valid camera scenes in a single file remain a documented limitation. Temporal segmentation is deferred.


## Failure and reporting policy

**Processing failures**

These conditions terminate the job immediately with an error:

- The input video cannot be opened.
- Video metadata is implausible, such as a non-positive frame count or dimensions smaller than two pixels.
- No valid detections remain after all samples are processed.

Individual seek or read failures are handled differently. OpenCV cannot always distinguish a true end-of-file from a decode error or inaccurate metadata. Isolated failures are logged, counted and skipped. Unexpected exceptions outside this category propagate. `VideoCapture` is always released in `finally`.

**Reporting**

Progress is sent to `POST /api/v1/jobs/progress`. Terminal outcomes are sent to `POST /api/v1/jobs/events`.

The mock server enforces no schema. Payloads are validated client-side before sending. A response is accepted only when it returns HTTP `200` with `{"status": "received"}`.

Timeouts and attempt counts are bounded by configuration. Connection errors, timeouts and `5xx` responses are retried. `4xx` responses are not retried. Retries use a stable `event_id` to reduce ambiguity, but the mock API provides no idempotency enforcement. Duplicate stored events are possible.

If a progress retry cycle exhausts all attempts, further progress calls are disabled for that job. Processing continues. Terminal reporting is still attempted. A reporting failure is not a pipeline failure.

**Exit codes**

| Exit code | Meaning |
|---|---|
| `0` | Pipeline and required reporting succeeded |
| `1` | Configuration failed |
| `2` | Video pipeline failed |
| `3` | Pipeline completed, but reporting was degraded or failed |


## Verification

```powershell
python -m pytest -q
```

Verified result: `33 passed`.

**Actually run:**

- Original 1,800-frame prototype run
- Corrected local processing after detector fix
- 1,800-frame and 3,600-frame timing runs
- Docker image build
- Containerized end-to-end run with 120 samples, 116 valid detections, 4 invalid, zero decode failures
- Completion event retrieved from `GET /api/v1/jobs/events`

**Covered by focused tests:**

- Strict configuration validation
- Detector validity and noise rejection
- Fixed-budget sampling
- Aggregation and median-area selection
- Zero-detection termination
- Capture cleanup on error
- Unexpected exception propagation
- Reporting retries and failure behavior
- Exit code separation

**Not executed or deferred:**

- Real corrupted-stream behavior
- Live-stream processing
- Production ML detector output
- External API authentication and idempotency
- Broader platform and codec testing


## Performance observations

Input generation was excluded from all measurements. These are single-run observations, not a benchmark.

| Environment    | Total frames | Samples | Time     |
|----------------|-------------|---------|----------|
| Local Python   | 1,800       | 120     | 1.4413 s |
| Local Python   | 3,600       | 120     | 1.3879 s |
| Docker Compose | 1,800       | 120     | 1.7957 s |

Detector calls stayed at 120 across all runs. Seek and I/O cost depends on keyframe spacing and varies by codec. These results do not prove constant-time processing.

See [DECISIONS.md](DECISIONS.md) for the full trade-off discussion.


## Limitations and deferred work

- The white-line detector is synthetic-data-specific. It is not a production segmentation model.
- Only finite, seekable files are supported. Live streams are not.
- There is no temporal grouping across valid camera cuts. Multiple angles in one file are handled by picking one observed polygon.
- Crop-layout optimization is not implemented.
- The supplied mock API is in-memory, unauthenticated and enforces no idempotency.
- There is no exactly-once reporting guarantee.
- Performance evidence comes from single runs only.
- Structured metrics, tracing and broader codec and platform tests are deferred.


## Decisions and AI disclosure

[DECISIONS.md](DECISIONS.md) covers architecture trade-offs, configuration decisions, detection rationale, sampling behavior, aggregation policy, reporting guarantees, open questions and the full AI-use disclosure.

The project PDF includes a general restriction on AI assistance. The `ASSIGNMENT.md` document explicitly encourages disclosed LLM use as part of the evaluation. These instructions conflict. The detailed assignment document was treated as the controlling one, but this discrepancy should be confirmed with the recruiter before the submission is assessed.
