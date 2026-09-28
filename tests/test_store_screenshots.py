# SPDX-License-Identifier: GPL-3.0-only
import os
import struct
import tempfile
import unittest
from pathlib import Path

from store_screenshots import (
    KitError,
    load_config,
    parse_result_links,
    png_info,
    validate_screenshots,
)


def minimal_png(width: int, height: int, color_type: int = 2) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + bytes((8, color_type, 0, 0, 0))
    )


class ScreenshotKitTest(unittest.TestCase):
    def test_parses_firebase_links(self) -> None:
        output = """
        Raw results will be stored at
        [https://console.developers.google.com/storage/browser/test-bucket/run-123/]
        More details at
        [ https://console.firebase.google.com/project/demo/testlab/histories/1/matrices/2 ].
        """
        matrix, prefix = parse_result_links(output)
        self.assertEqual(
            matrix,
            "https://console.firebase.google.com/project/demo/testlab/histories/1/matrices/2",
        )
        self.assertEqual(prefix, "gs://test-bucket/run-123")

    def test_reads_png_header(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "screen.png"
            path.write_bytes(minimal_png(1600, 2560))
            self.assertEqual(png_info(path), (1600, 2560, 2))

    def test_validates_count_size_and_rgb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for index in range(2):
                (directory / f"{index}.png").write_bytes(minimal_png(1600, 2560))
            files = validate_screenshots(
                directory,
                {"expected_count": 2, "width": 1600, "height": 2560, "require_rgb": True},
            )
            self.assertEqual(len(files), 2)

    def test_rejects_alpha_png_when_rgb_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "screen.png").write_bytes(minimal_png(1600, 2560, color_type=6))
            with self.assertRaises(KitError):
                validate_screenshots(
                    directory,
                    {
                        "expected_count": 1,
                        "width": 1600,
                        "height": 2560,
                        "require_rgb": True,
                    },
                )

    def test_expands_project_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "kit.toml"
            path.write_text(
                """
                [app]
                root = "."
                build = ["true"]
                app_apk = "app.apk"
                test_apk = "test.apk"
                package_name = "dev.example"
                test_target = "class dev.example.Test"
                remote_directory = "/sdcard/screenshots"
                results_dir = "results"

                [firebase]
                project = "${SCREENSHOT_TEST_PROJECT}"
                history_name = "Screenshots"
                timeout = "5m"

                [validation]
                expected_count = 1
                width = 100
                height = 200

                [[devices]]
                id = "tablet"
                model = "tablet"
                version = "35"
                locale = "en"
                orientation = "portrait"
                """,
                encoding="utf-8",
            )
            old = os.environ.get("SCREENSHOT_TEST_PROJECT")
            os.environ["SCREENSHOT_TEST_PROJECT"] = "demo-project"
            try:
                self.assertEqual(load_config(path)["firebase"]["project"], "demo-project")
            finally:
                if old is None:
                    del os.environ["SCREENSHOT_TEST_PROJECT"]
                else:
                    os.environ["SCREENSHOT_TEST_PROJECT"] = old


if __name__ == "__main__":
    unittest.main()
