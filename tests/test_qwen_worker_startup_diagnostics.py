from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from app.tts import qwen_character_worker as worker


class QwenWorkerStartupDiagnosticsTests(unittest.TestCase):
    def test_worker_diagnostic_writes_flushed_structured_stderr_record(self):
        output = io.StringIO()
        with (
            patch.object(worker.sys, "stderr", output),
            patch.object(worker.os, "getpid", return_value=2468),
            patch.object(
                worker.time,
                "monotonic",
                return_value=worker._WORKER_STARTED_AT + 1.25,
            ),
        ):
            worker._worker_diagnostic(
                "model_weights_load_begin",
                model_kind="design-1.7b",
                requested_backend="cpu",
                selected_device="cpu",
                weight_bytes=123456,
            )

        line = output.getvalue()
        self.assertTrue(line.endswith("\n"))
        self.assertTrue(line.startswith(worker._WORKER_DIAGNOSTIC_PREFIX))
        payload = json.loads(line[len(worker._WORKER_DIAGNOSTIC_PREFIX):])
        self.assertEqual(payload["event"], "model_weights_load_begin")
        self.assertEqual(payload["pid"], 2468)
        self.assertEqual(payload["elapsed_seconds"], 1.25)
        self.assertEqual(payload["model_kind"], "design-1.7b")
        self.assertEqual(payload["selected_device"], "cpu")
        self.assertEqual(payload["weight_bytes"], 123456)

    def test_diagnostic_failure_never_breaks_worker_operation(self):
        with patch("builtins.print", side_effect=OSError("diagnostic sink closed")):
            worker._worker_diagnostic("diagnostic_sink_unavailable", model_kind="design-1.7b")


if __name__ == "__main__":
    unittest.main()
