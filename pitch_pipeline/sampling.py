def uniform_frame_indices(total_frames: int, max_samples: int) -> list[int]:
    if total_frames <= 0 or max_samples <= 0:
        raise ValueError("total_frames and max_samples must be positive")

    sample_count = min(total_frames, max_samples)

    if sample_count == 1:
        return [0]

    return [
        int(i * (total_frames - 1) / (sample_count - 1)) for i in range(sample_count)
    ]
