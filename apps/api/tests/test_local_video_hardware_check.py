from scripts.local_video_hardware_check import assess_hardware


def test_four_gib_gpu_is_experimental_only_with_low_system_memory() -> None:
    report = assess_hardware(
        12 * 1024**3,
        [{"name": "NVIDIA GeForce RTX 2050", "vram_gib": 4.0, "driver_version": "test"}],
    )
    assert report["assessment_tier"] == "very_low_vram_experimental_only"
    assert "Do not download a large video checkpoint yet" in report["recommendation"]


def test_no_gpu_does_not_recommend_a_specific_local_video_checkpoint() -> None:
    report = assess_hardware(8 * 1024**3, [])
    assert report["assessment_tier"] == "hardware_not_confirmed"
    assert "No supported NVIDIA GPU" in report["recommendation"]


def test_high_memory_gpu_gets_candidate_not_guarantee_language() -> None:
    report = assess_hardware(
        64 * 1024**3,
        [{"name": "Test GPU", "vram_gib": 24.0, "driver_version": "test"}],
    )
    assert report["assessment_tier"] == "strong_local_video_candidate"
    assert any("not a benchmark" in item for item in report["limitations"])
