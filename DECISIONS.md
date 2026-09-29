# Engineering Decisions

## Scope and status

**Implemented:**
- A reusable finite-video processing library that the rest of the pipeline builds on
- A replaceable white-line detector behind a `FieldDetector` interface
- Strict JSON configuration with Pydantic validation
- Fixed-budget sampling using uniform seeking
- A validated reporting client for the platform API
- A thin CLI entry point
- A Docker Compose workflow for containerized execution

**Verified:**
- 33 pytest checks covering configuration, detection, aggregation, reporting and CLI behavior
- One containerized end-to-end run on a synthetic 1,800-frame clip: 120 samples taken, 116 valid detections, 4 flagged as invalid, zero decode failures, one completion event stored by the mock API

**Not implemented:**
- Downstream crop-layout optimization. The supplied README explicitly marks this as not implemented, so it was left out of scope.

**Deferred:**
- Live-stream sampling. It requires a different strategy than seek-based sampling.
- Production ML segmentation. The current detector is synthetic-data-specific and intended to be replaced.


## Detection approach and limitations

The prototype thresholded green pixels and selected the largest external contour. Inspecting an actual frame showed the problem. The returned bounds were `(0, 0, 1279, 719)` with area `919601`. The detector had found the image border, not a field. The geometry was valid. It was just the wrong polygon.

The replacement works differently. It thresholds the synthetic feed's white boundary markings, simplifies the contour with `approxPolyDP` and filters out small noise blobs via `min_area`. On a representative frame it returned four points with bounds `(50, 98, 1233, 623)`, inset from the edges.

This detector is tuned to the synthetic feed's white lines. It is not a general field detector. The `FieldDetector` interface exists so a production implementation with actual segmentation can drop in without touching the rest of the pipeline.

No confidence score is reported. This detector does not produce one and inventing a placeholder would be misleading.


## Configuration and validation

Every top-level and nested Pydantic model uses `extra="forbid"` and validates its default values. The assignment calls for fail-fast behavior. Silent misconfiguration is hard to debug after the fact.

Validation catches all of the following before a frame is ever read: unsupported detector types, out-of-range parameter values, malformed API URLs, blank job IDs, malformed JSON files and unreadable config files. Defaults apply when optional fields are omitted. They do not apply when a field is explicitly set to something invalid.

Configuration comes from a single JSON file, selected via `--config` or the `PIPELINE_CONFIG` environment variable. This avoids the ambiguity of per-field environment variable parsing.

Three prototype settings were removed:

- `target_fps` — replaced by `max_samples`, which bounds work directly rather than deriving a sample count from duration
- `confidence_threshold` — the replacement detector does not produce a confidence score
- Sport/model metadata and `crop_search` — the implementation never used them. Keeping unused config fields would imply behavior that does not exist.


## Sampling and performance

The sampler seeks to uniformly distributed positions across the file. It calls the detector at most `max_samples` times. With fixed-rate sampling, detector calls grow with video duration. The fixed inspection budget caps detector calls, although total I/O and seek time can still vary.

Seeking is not free. Codecs decode from the nearest keyframe. Decoding and I/O cost depends on keyframe spacing and varies by codec. A fixed budget means fixed detector calls, not constant wall time.

Live streams cannot use this strategy. Seeking requires a finite, seekable file. Live-stream support is deferred.

A few things were cleaned up from the prototype. The artificial 5 ms inter-frame delay is gone. Video dimensions are read once per file, not per frame. The frame boundary is constructed once and reused. Input generation was excluded from timing.

Single-run observations, not a benchmark:

| Environment    | Total frames | Samples | Time     |
|----------------|-------------|---------|----------|
| Local Python   | 1,800       | 120     | 1.4413 s |
| Local Python   | 3,600       | 120     | 1.3879 s |
| Docker Compose | 1,800       | 120     | 1.7957 s |

The 3,600-frame run coming in slightly under the 1,800-frame run is within single-run noise. These observations confirm the same 120-call detector budget on both files. They do not prove runtime is independent of duration.


## Aggregation and failure handling

A detection enters the candidate pool only if it is a non-empty, valid `Polygon` with positive area after clipping to the actual frame boundary. Missing, noisy, or geometrically implausible results are counted and excluded. The pool is bounded by `max_samples`.

The representative polygon is the candidate closest to the median valid area. Averaging vertices across different camera views would produce a shape that matches no real view. This approach picks an observed polygon instead. It does not fully solve the problem of multiple valid camera angles. Properly handling view cuts requires temporal segmentation, which is deferred.

Three conditions terminate the job with an explicit error: unreadable input, non-positive frame count or implausible dimensions and zero valid detections after all samples are attempted.

Individual seek or read failures are handled differently. OpenCV cannot always distinguish true EOF from a decode error or inaccurate frame-count metadata. Isolated failures are logged, counted and skipped rather than treated as fatal. Unexpected errors outside this category propagate normally. Capture release always runs in `finally`.


## Platform reporting

Progress goes to `POST /api/v1/jobs/progress`. Terminal outcomes go to `POST /api/v1/jobs/events`.

The mock API accepts arbitrary JSON. The payload structure is a client-side design decision, not something the server validates. A real integration would need the actual schema.

A response is accepted as successful only when it returns HTTP `200` with `{"status": "received"}`. Connection errors, timeouts and `5xx` responses are retried up to a bounded number of attempts. `4xx` responses are not retried. They indicate a client-side problem that will not resolve on its own.

Retries use a stable `event_id`. That is best-effort, not a guarantee. The mock API has no idempotency key support, so a retry can still produce a duplicate stored event.

If a progress retry cycle exhausts all attempts, further progress calls are disabled for that job. Processing continues. Terminal reporting is still attempted. A reporting failure is not a pipeline failure.

Exit codes: `1` for configuration errors, `2` for pipeline errors, `3` for reporting errors.

Compose health checks handle startup readiness. Client retries cover transient failures during a run.


## Assumptions and open questions

**Assumptions baked into the current implementation:**
- Inputs are finite, seekable files with usable frame-count metadata. The entire sampling strategy depends on this.

**Questions for product/ML teams:**

- What combination of accuracy, latency and coverage should drive `max_samples`? The current default is a guess.
- What does production detector output look like? What confidence calibration is expected? What are the boundary semantics — field interior, line markings, or something else?
- Is zero valid detections a failed job or a valid "no field visible" result? These need different exit behavior and different reporting.
- How should valid camera cuts be handled? The current approach picks one representative polygon. If the feed shows multiple angles, that choice is arbitrary.
- What is the real API schema? What authentication does it require? Are there idempotency keys or duplicate-handling guarantees?
- Is crop-layout calculation expected to live in a later component of this pipeline?


## Deferred work

- Production segmentation with calibrated confidence.
- Scene-change detection and temporal grouping before aggregation.
- A separate sampling strategy for live streams.
- Repeated benchmarks across codecs, keyframe layouts, resolutions, and hardware.
- Production observability such as structured metrics, tracing, and alerting.
- A downstream crop-layout optimizer after its contract is clarified.


## AI/LLM disclosure

I used OpenAI ChatGPT as a step-by-step mentor throughout this assignment. It helped with interpreting requirements where the PDF and `ASSIGNMENT.md` conflicted, understanding what was wrong with the original detector, discussing architecture trade-offs, reviewing code I had written, suggesting focused tests, diagnosing failures, Docker configuration and reviewing this documentation.

I wrote and adapted the implementation in VS Code. I handled project setup, ran every command, executed the test suite and benchmarks, ran the container, verified the results, committed and pushed. The AI supplied explanations, examples, review feedback and help with wording. It did not write code independently or run anything.

The PDF prohibits AI assistance unless explicitly permitted. The `ASSIGNMENT.md` says disclosed LLM use is part of the evaluation. I treated the more detailed, assignment-specific document as the controlling one. I will flag the discrepancy to the recruiter rather than assume I interpreted it correctly.
