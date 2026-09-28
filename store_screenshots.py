#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Build, run, download, and validate Android store screenshots."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Iterable


class KitError(RuntimeError):
    """A user-actionable pipeline failure."""


def expand_environment(value: Any) -> Any:
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        if "${" in expanded:
            raise KitError(f"Unresolved environment variable in: {value}")
        return expanded
    if isinstance(value, list):
        return [expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_environment(item) for key, item in value.items()}
    return value


def load_config(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise KitError(f"Configuration file does not exist: {path}")
    with path.open("rb") as handle:
        config = expand_environment(tomllib.load(handle))

    for section in ("app", "firebase", "validation", "devices"):
        if section not in config:
            raise KitError(f"Configuration is missing [{section}]")

    app = config["app"]
    firebase = config["firebase"]
    required_app = (
        "root",
        "build",
        "app_apk",
        "test_apk",
        "package_name",
        "test_target",
        "remote_directory",
        "results_dir",
    )
    for key in required_app:
        if not app.get(key):
            raise KitError(f"Configuration is missing app.{key}")
    for key in ("project", "history_name", "timeout"):
        if not firebase.get(key):
            raise KitError(f"Configuration is missing firebase.{key}")
    if not isinstance(app["build"], list) or not all(
        isinstance(part, str) for part in app["build"]
    ):
        raise KitError("app.build must be an array of command arguments")
    if not isinstance(config["devices"], list) or not config["devices"]:
        raise KitError("At least one [[devices]] entry is required")

    root = Path(app["root"])
    if not root.is_absolute():
        root = path.parent / root
    app["root"] = str(root.resolve())
    config["_config_path"] = str(path)
    return config


def select_device(config: dict[str, Any], device_id: str) -> dict[str, str]:
    matches = [device for device in config["devices"] if device.get("id") == device_id]
    if not matches:
        names = ", ".join(str(device.get("id")) for device in config["devices"])
        raise KitError(f"Unknown device '{device_id}'. Configured devices: {names}")
    device = matches[0]
    for key in ("model", "version", "locale", "orientation"):
        if not device.get(key):
            raise KitError(f"Device '{device_id}' is missing {key}")
    return {key: str(value) for key, value in device.items()}


def resolve_app_path(config: dict[str, Any], key: str) -> Path:
    path = Path(config["app"][key])
    if not path.is_absolute():
        path = Path(config["app"]["root"]) / path
    return path.resolve()


def require_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise KitError(f"Required executable is not on PATH: {name}")
    return executable


def run_checked(command: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(command)
    print(f"+ {printable}", flush=True)
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise KitError(f"Command failed with exit code {result.returncode}: {printable}")


def stream_command(command: list[str], cwd: Path, log_path: Path) -> tuple[int, str]:
    printable = " ".join(command)
    print(f"+ {printable}", flush=True)
    lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            lines.append(line)
        return process.wait(), "".join(lines)


def parse_result_links(output: str) -> tuple[str | None, str | None]:
    matrix_matches = re.findall(
        r"https://console\.firebase\.google\.com/[^\s\]]+", output
    )
    matrix_url = matrix_matches[-1].rstrip(".,") if matrix_matches else None

    browser_matches = re.findall(
        r"https://console\.(?:developers\.google\.com|cloud\.google\.com)"
        r"/storage/browser/([^/\s\]]+)(/[^\s\]]*)?",
        output,
    )
    if browser_matches:
        bucket, suffix = browser_matches[-1]
        return matrix_url, ("gs://" + bucket + (suffix or "")).rstrip("/")

    gs_matches = re.findall(r"gs://[^\s\]]+", output)
    gcs_prefix = gs_matches[-1].rstrip("/.,") if gs_matches else None
    return matrix_url, gcs_prefix


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_info(path: Path) -> tuple[int, int, int]:
    with path.open("rb") as handle:
        header = handle.read(29)
    if len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise KitError(f"Not a PNG file: {path}")
    if header[12:16] != b"IHDR":
        raise KitError(f"PNG has no leading IHDR chunk: {path}")
    width, height = struct.unpack(">II", header[16:24])
    color_type = header[25]
    return width, height, color_type


def validate_screenshots(directory: Path, validation: dict[str, Any]) -> list[Path]:
    directory = directory.resolve()
    files = sorted(directory.glob("*.png"))
    expected_count = int(validation["expected_count"])
    if len(files) != expected_count:
        raise KitError(f"Expected {expected_count} PNG files in {directory}, found {len(files)}")

    expected_size = (int(validation["width"]), int(validation["height"]))
    require_rgb = bool(validation.get("require_rgb", True))
    errors: list[str] = []
    for path in files:
        width, height, color_type = png_info(path)
        if (width, height) != expected_size:
            errors.append(f"{path.name}: {width}x{height}, expected {expected_size[0]}x{expected_size[1]}")
        if require_rgb and color_type != 2:
            errors.append(f"{path.name}: PNG color type {color_type}, expected opaque RGB (2)")
    if errors:
        raise KitError("Screenshot validation failed:\n  " + "\n  ".join(errors))

    print(
        f"Validated {len(files)} PNG files at {expected_size[0]}x{expected_size[1]}"
        + (" opaque RGB" if require_rgb else ""),
        flush=True,
    )
    return files


def download_screenshots(
    gcloud: str,
    gcs_prefix: str,
    remote_directory: str,
    destination: Path,
) -> list[Path]:
    listing = subprocess.run(
        [gcloud, "storage", "ls", "--recursive", f"{gcs_prefix}/**"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode:
        raise KitError(f"Could not list Test Lab artifacts:\n{listing.stderr.strip()}")

    marker = "/artifacts" + remote_directory.rstrip("/") + "/"
    uris = sorted(
        line.strip()
        for line in listing.stdout.splitlines()
        if marker in line and line.strip().lower().endswith(".png")
    )
    if not uris:
        raise KitError(
            "No screenshots found under the configured remote directory. "
            f"Expected an artifact path containing: {marker}"
        )

    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for uri in uris:
        target = destination / Path(uri).name
        run_checked([gcloud, "storage", "cp", uri, str(target)])
        downloaded.append(target)
    return downloaded


def publish_screenshots(files: Iterable[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    for source in files:
        target = destination / source.name
        shutil.copy2(source, target)
        published.append(target)
    print(f"Published {len(published)} screenshots to {destination}", flush=True)
    return published


def find_zipalign() -> str:
    direct = shutil.which("zipalign")
    if direct:
        return direct
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk:
        candidates = sorted(Path(sdk).glob("build-tools/*/zipalign"), reverse=True)
        if candidates:
            return str(candidates[0])
    raise KitError("zipalign was not found on PATH or under ANDROID_HOME/build-tools")


def verify_apk(apk: Path) -> None:
    apk = apk.resolve()
    if not apk.is_file():
        raise KitError(f"APK does not exist: {apk}")
    run_checked([find_zipalign(), "-c", "-P", "16", "4", str(apk)])

    readelf = require_executable("readelf")
    failures: list[str] = []
    checked = 0
    with zipfile.ZipFile(apk) as archive, tempfile.TemporaryDirectory() as temporary:
        for member in sorted(name for name in archive.namelist() if name.endswith(".so")):
            target = Path(temporary) / Path(member).name
            target.write_bytes(archive.read(member))
            result = subprocess.run(
                [readelf, "-lW", str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                failures.append(f"{member}: readelf failed")
                continue
            aligns = []
            for line in result.stdout.splitlines():
                if line.lstrip().startswith("LOAD "):
                    aligns.append(int(line.split()[-1], 16))
            if not aligns:
                failures.append(f"{member}: no ELF LOAD segments found")
                continue
            checked += 1
            if min(aligns) < 16_384:
                failures.append(f"{member}: minimum LOAD alignment is 0x{min(aligns):x}")
    if failures:
        raise KitError("APK native alignment failed:\n  " + "\n  ".join(failures))
    print(f"APK is ZIP aligned and {checked} native libraries use >=16 KB LOAD alignment")


def run_pipeline(config: dict[str, Any], device_id: str, no_build: bool) -> None:
    app = config["app"]
    firebase = config["firebase"]
    device = select_device(config, device_id)
    root = Path(app["root"])
    gcloud = require_executable(str(firebase.get("gcloud", "gcloud")))

    if not no_build:
        run_checked(list(app["build"]), cwd=root)

    app_apk = resolve_app_path(config, "app_apk")
    test_apk = resolve_app_path(config, "test_apk")
    for path in (app_apk, test_apk):
        if not path.is_file():
            raise KitError(f"Built APK does not exist: {path}")

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    results_root = resolve_app_path(config, "results_dir")
    run_directory = results_root / f"{timestamp}-{device_id}"
    screenshots_directory = run_directory / "screenshots"
    run_directory.mkdir(parents=True, exist_ok=False)

    axis = ",".join(
        f"{key}={device[key]}" for key in ("model", "version", "locale", "orientation")
    )
    command = [
        gcloud,
        "firebase",
        "test",
        "android",
        "run",
        f"--project={firebase['project']}",
        "--type=instrumentation",
        f"--app={app_apk}",
        f"--test={test_apk}",
        f"--test-targets={app['test_target']}",
        f"--device={axis}",
        f"--timeout={firebase['timeout']}",
        f"--results-history-name={firebase['history_name']}",
        f"--directories-to-pull={app['remote_directory']}",
        "--format=json",
    ]
    returncode, output = stream_command(command, root, run_directory / "gcloud.log")
    matrix_url, gcs_prefix = parse_result_links(output)

    manifest: dict[str, Any] = {
        "created_at": timestamp,
        "device": device,
        "firebase_project": firebase["project"],
        "matrix_url": matrix_url,
        "gcs_prefix": gcs_prefix,
        "app_apk": str(app_apk),
        "app_apk_sha256": sha256(app_apk),
        "test_apk": str(test_apk),
        "test_apk_sha256": sha256(test_apk),
        "test_target": app["test_target"],
        "remote_directory": app["remote_directory"],
        "exit_code": returncode,
    }
    (run_directory / "run.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    if returncode:
        raise KitError(
            f"Firebase Test Lab failed with exit code {returncode}. Artifacts: {run_directory}"
        )
    if not gcs_prefix:
        raise KitError(
            "Test passed but the GCS result prefix could not be parsed. "
            f"Inspect {run_directory / 'gcloud.log'}"
        )

    files = download_screenshots(
        gcloud, gcs_prefix, app["remote_directory"], screenshots_directory
    )
    files = validate_screenshots(screenshots_directory, config["validation"])
    manifest["screenshots"] = [
        {"name": path.name, "sha256": sha256(path)} for path in files
    ]

    if app.get("publish_dir"):
        publish_dir = resolve_app_path(config, "publish_dir")
        publish_screenshots(files, publish_dir)
        validate_screenshots(publish_dir, config["validation"])
        manifest["publish_dir"] = str(publish_dir)

    (run_directory / "run.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Run manifest: {run_directory / 'run.json'}")
    if matrix_url:
        print(f"Firebase result: {matrix_url}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="build and execute one Test Lab device axis")
    run.add_argument("--config", type=Path, default=Path("screenshot-kit.toml"))
    run.add_argument("--device", required=True, help="configured device id")
    run.add_argument("--no-build", action="store_true", help="reuse existing APKs")

    validate = subparsers.add_parser("validate", help="validate a screenshot directory")
    validate.add_argument("directory", type=Path)
    validate.add_argument("--config", type=Path, default=Path("screenshot-kit.toml"))

    verify = subparsers.add_parser("verify-apk", help="check APK 16 KB alignment")
    verify.add_argument("apk", type=Path)

    show = subparsers.add_parser("show-config", help="print resolved configuration")
    show.add_argument("--config", type=Path, default=Path("screenshot-kit.toml"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "verify-apk":
            verify_apk(args.apk)
        else:
            config = load_config(args.config)
            if args.command == "run":
                run_pipeline(config, args.device, args.no_build)
            elif args.command == "validate":
                validate_screenshots(args.directory, config["validation"])
            elif args.command == "show-config":
                print(json.dumps(config, indent=2))
        return 0
    except KitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
