from transcrever_app.asr.faster_whisper import ASRModelRegistry


class FakeModel:
    """Minimal registry-compatible model."""

    calls = 0

    def __init__(self, _name: str, *, device: str, compute_type: str) -> None:
        """Record model construction."""
        _ = (device, compute_type)
        type(self).calls += 1

    def transcribe(
        self,
        _audio: str,
        *,
        language: str,
        beam_size: int,
        vad_filter: bool,
        word_timestamps: bool,
        condition_on_previous_text: bool,
    ) -> tuple[tuple[()], object]:
        """Return an empty adapter-compatible result."""
        _ = (language, beam_size, vad_filter, word_timestamps, condition_on_previous_text)
        return (), object()


def test_registry_reuses_compatible_model_and_reloads_other_configuration() -> None:
    FakeModel.calls = 0
    registry = ASRModelRegistry()

    first = registry.get(
        model_name="large-v3",
        device="cuda",
        compute_type="float16",
        model_type=FakeModel,
    )
    second = registry.get(
        model_name="large-v3",
        device="cuda",
        compute_type="float16",
        model_type=FakeModel,
    )
    third = registry.get(
        model_name="small",
        device="cuda",
        compute_type="float16",
        model_type=FakeModel,
    )

    assert first is second
    assert third is not first
    expected_model_count = 2
    assert FakeModel.calls == expected_model_count
