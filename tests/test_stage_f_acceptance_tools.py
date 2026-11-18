from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from app.chapters.characters import analyze_book
from app.chapters.detector import Chapter
from app.chapters.passage_index import build_passage_index


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = ROOT / "scripts" / "stage_f_capture_environment.ps1"


class StageFAcceptanceToolTests(unittest.TestCase):
    def test_capture_script_pins_the_accepted_build_3470_binary_hashes(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8").casefold()
        self.assertIn("fc3a0f8e1d64790b1a61024f8d883653b2dad51c", source)
        self.assertIn("29e733e73c1d19b21aa89e512fd4b7ff5f7160b2d492b791c224d0ebdbee699c", source)
        self.assertIn("d759411795704cbbc69539616c81797b23bd5313e80b5474a13461bd053f5512", source)
        self.assertIn("0af7f21d1d379ed65e7d9aa166e2ccbb72c85aa85ecfec136bb5369f5dd77110", source)

    def test_capture_script_does_not_collect_machine_or_network_identifiers(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        forbidden = (
            "Win32_BIOS",
            "SerialNumber",
            "MachineGuid",
            "Win32_NetworkAdapter",
            "Get-NetAdapter",
            "$env:USERNAME",
            "$env:COMPUTERNAME",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token.casefold(), source.casefold())
        for token in (
            "machine_identity_included = $false",
            "user_account_names_included = $false",
            "serial_numbers_included = $false",
            "network_identifiers_included = $false",
            "absolute_paths_included = $false",
            "voice_audio_contents_included = $false",
        ):
            self.assertIn(token, source)

    def test_capture_script_never_claims_hardware_inventory_is_inference_evidence(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("hardware_discovery_is_inference_evidence = $false", source)
        self.assertIn("resolved_qwen_backend = 'NOT_CAPTURED_BY_THIS_TOOL'", source)
        self.assertIn("nvidia_smi_available", source)
        self.assertIn("rocm_smi_available", source)
        self.assertIn("xpu_smi_available", source)

    def test_single_result_wmi_queries_are_normalized_before_count_access(self):
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("$osRows = @(Get-CimRows -ClassName 'Win32_OperatingSystem')", source)
        self.assertIn("$computerRows = @(Get-CimRows -ClassName 'Win32_ComputerSystem')", source)
        self.assertIn("$driveRows = @(Get-CimInstance -ClassName 'Win32_LogicalDisk'", source)

    def test_passage_counters_are_distinct_metrics_for_unquoted_saved_assignments(self):
        source_text = "Mira answered without quotation marks."
        chapter = Chapter(1, "Unquoted assigned dialogue", source_text)
        chapter.dialogue_assignments = [
            {
                "start": 0,
                "end": len(source_text),
                "text": source_text,
                "speaker": "Mira",
                "source": "manual",
            }
        ]

        legacy_quote_span_count = analyze_book([chapter]).dialogue_total
        canonical_index = build_passage_index([chapter])
        canonical_dialogue_rows = [row for row in canonical_index["passages"] if row["dialogue"]]

        self.assertEqual(legacy_quote_span_count, 0)
        self.assertEqual(canonical_index["counts"]["dialogue_passage_count"], 1)
        self.assertEqual(len(canonical_dialogue_rows), 1)
        self.assertEqual(canonical_dialogue_rows[0]["kind"], "character_dialogue")
        self.assertEqual(canonical_dialogue_rows[0]["source"], "manual")
        self.assertEqual(
            source_text[canonical_dialogue_rows[0]["start"]:canonical_dialogue_rows[0]["end"]],
            source_text,
        )

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell is required for this integration test")
    def test_windows_capture_report_succeeds_without_optional_file_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path = root / "stage-f-environment.json"
            command = [
                shutil.which("powershell.exe"),
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(CAPTURE_SCRIPT),
                "-Role", "CI",
                "-OutputPath", str(report_path),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + "\\n" + completed.stderr)
            self.assertTrue(report_path.is_file())
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertEqual(report["result"], "CAPTURED")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["evidence_files"], [])
            self.assertFalse(report["privacy"]["user_account_names_included"])
            self.assertFalse(report["privacy"]["serial_numbers_included"])
            self.assertFalse(report["privacy"]["network_identifiers_included"])
            self.assertFalse(report["privacy"]["voice_audio_contents_included"])
            self.assertNotIn(str(root), report_text)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell is required for this integration test")
    def test_windows_capture_report_is_written_and_does_not_embed_input_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path = root / "stage-f-environment.json"
            fake_exe = root / "deliberately-wrong.exe"
            fake_exe.write_bytes(b"not the accepted executable")

            command = [
                shutil.which("powershell.exe"),
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(CAPTURE_SCRIPT),
                "-Role", "CI",
                "-OutputPath", str(report_path),
                "-ApplicationExePath", str(fake_exe),
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )

            self.assertEqual(completed.returncode, 2, completed.stdout + "\n" + completed.stderr)
            self.assertTrue(report_path.is_file())
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)

            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["role"], "CI")
            self.assertEqual(report["accepted_application_baseline"]["build_number"], 3470)
            self.assertEqual(
                report["accepted_application_baseline"]["source_commit"],
                "fc3a0f8e1d64790b1a61024f8d883653b2dad51c",
            )
            self.assertFalse(report["limitations"]["hardware_discovery_is_inference_evidence"])
            self.assertEqual(report["limitations"]["resolved_qwen_backend"], "NOT_CAPTURED_BY_THIS_TOOL")
            self.assertFalse(report["privacy"]["user_account_names_included"])
            self.assertFalse(report["privacy"]["absolute_paths_included"])
            self.assertFalse(report["privacy"]["voice_audio_contents_included"])

            app_record = next(item for item in report["evidence_files"] if item["kind"] == "application_exe")
            self.assertEqual(app_record["status"], "hash_mismatch", json.dumps({"app_record": app_record, "errors": report["errors"]}))
            self.assertFalse(app_record["matches_expected"])
            self.assertNotIn(str(root), report_text)
            self.assertNotIn(fake_exe.name, report_text)


if __name__ == "__main__":
    unittest.main()
