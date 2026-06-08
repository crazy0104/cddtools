import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CDD = PROJECT_ROOT / "examples" / "Multilingual-Example.cdd"


class CliTests(unittest.TestCase):
    def test_module_cli_prints_version(self):
        completed = subprocess.run(
            [sys.executable, "-m", "cddtools", "--version"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "cddtools 0.0.1")

    def test_module_cli_writes_json_to_stdout(self):
        completed = subprocess.run(
            [sys.executable, "-m", "cddtools", "parseDids", str(EXAMPLE_CDD)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout)
        self.assertEqual(result["error"], 0)
        self.assertEqual(len(result["data"]), 2)

    def test_module_cli_writes_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "out.json"

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cddtools",
                    "parse",
                    str(EXAMPLE_CDD),
                    str(output_path),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["error"], 0)
        self.assertIn("data", result)


if __name__ == "__main__":
    unittest.main()
