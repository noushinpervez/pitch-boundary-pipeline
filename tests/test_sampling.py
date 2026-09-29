import pytest

from pitch_pipeline.sampling import uniform_frame_indices


def test_long_video_respects_budget_and_covers_endpoints():
    indices = uniform_frame_indices(total_frames=100, max_samples=5)

    assert len(indices) == 5
    assert indices == sorted(set(indices))
    assert indices[0] == 0
    assert indices[-1] == 99


def test_short_video_returns_every_frame():
    indices = uniform_frame_indices(total_frames=4, max_samples=10)

    assert indices == [0, 1, 2, 3]


@pytest.mark.parametrize(
    ("total_frames", "max_samples"),
    [
        (0, 5),
        (-1, 5),
        (10, 0),
        (10, -1),
        (0, 0),
    ],
)
def test_invalid_inputs_raise_value_error(total_frames, max_samples):
    with pytest.raises(ValueError):
        uniform_frame_indices(total_frames, max_samples)
