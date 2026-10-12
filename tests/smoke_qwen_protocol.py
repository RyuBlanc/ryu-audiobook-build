from __future__ import annotations

from pathlib import Path
import tempfile

from app.tts import qwen_character_worker as worker
from app.tts.expression import classify_expression, reference_style


class FakeVoiceDesignModel:
    def __init__(self):
        self.calls = []

    def generate_voice_design(self, text, language, instruct, **kwargs):
        self.calls.append((text, language, instruct, kwargs))
        count = len(text) if isinstance(text, list) else 1
        import numpy as np
        return [np.zeros(2400, dtype=np.float32) for _ in range(count)], 24000


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        request = {
            "speaker": "Test",
            "language": "English",
            "instruct": "Young adult male; natural audiobook narrator.",
            "seed": 123,
            "anchor_text": "Hello. This is a short, clear, natural voice test.",
        }
        model = FakeVoiceDesignModel()
        original_set_seed = worker._set_seed
        worker._set_seed = lambda seed: None
        try:
            paths = worker._create_expression_anchors(model, request, root)
        finally:
            worker._set_seed = original_set_seed
        assert set(paths) == {"neutral"}
        assert len(model.calls) == 1, "Canonical character identity must be generated once."
        assert all(call[0] and not isinstance(call[0], list) for call in model.calls)
        assert classify_expression("Instead of me…then?") == "thoughtful"
        assert reference_style("concerned") == "concerned"
        assert reference_style("excited") == "warm"

    print("Qwen expression protocol smoke PASSED.")


if __name__ == "__main__":
    main()
