# Android Store Screenshot Kit

A reusable Firebase Test Lab pipeline for producing deterministic Google Play
screenshots from real Android applications.

The kit owns the repeatable infrastructure:

- building app and instrumentation APKs;
- submitting an instrumentation test to configured Firebase devices;
- following the Test Lab matrix and preserving its Console URL;
- discovering and downloading screenshots from the result bucket;
- validating PNG count, dimensions, and color format;
- checking APK ZIP and native-library alignment for 16 KB Android devices;
- shared UI Automator operations for waiting, tapping, dismissing system UI,
  fixing orientation, and capturing screenshots.

Each application retains a small instrumentation test that knows how to seed its
own data and navigate its own screens. This division keeps product internals out
of the shared tool while avoiding repeated cloud and artifact plumbing.

## Requirements

- Python 3.11 or newer
- Android SDK build tools (`zipalign`)
- GNU `readelf`
- Google Cloud CLI with the Firebase Test Lab component
- A Google Cloud project with Firebase Test Lab enabled
- An Android instrumentation APK whose test writes PNGs into an app-scoped
  external directory

The included harness is Java-based and does not impose a Kotlin plugin version
on consuming Android projects. Its standalone build uses AGP 9, while the module
can also be included in an AGP 8 application build.

No Python packages are required.

## Quick start

1. Add this repository beside the Android application, or add it as a Git
   submodule under the application repository.
2. Copy `examples/screenshot-kit.toml` into the application repository and edit
   its paths, package name, test target, and device axes.
3. Copy `templates/PlayStoreScreenshotTest.kt` into the app's `androidTest`
   source set. Replace the fixture setup and navigation with app-specific code.
4. Optionally include the `harness` Android library as described in
   `docs/INTEGRATION.md`.
5. Authenticate the Google Cloud CLI and export the project identifier:

   ```bash
   export FIREBASE_PROJECT="your-project-id"
   gcloud auth login
   ```

6. Run one explicitly named device profile:

   ```bash
   /path/to/android-store-screenshot-kit/bin/store-screenshots \
     run --config screenshot-kit.toml --device pixel-tablet
   ```

The device must be named explicitly because physical Test Lab runs can consume
billed quota. Use `--no-build` to reuse APKs that were already built.

## Other commands

Validate a prepared screenshot directory:

```bash
bin/store-screenshots validate play-store/screenshots/tablet \
  --config screenshot-kit.toml
```

Check APK ZIP alignment and every packaged native library's ELF LOAD alignment:

```bash
bin/store-screenshots verify-apk path/to/app.apk
```

Print the resolved configuration without submitting a test:

```bash
bin/store-screenshots show-config --config screenshot-kit.toml
```

## Outputs

Every run receives its own local directory. It contains the unmodified PNGs and
`run.json`, which records hashes, the selected device, the Firebase Console URL,
the GCS result prefix, and the exact test configuration. When `publish_dir` is
configured, validated PNGs are also copied into that application-owned folder.

Credentials are never read from the config beyond normal Google Cloud CLI
authentication. Use environment substitution such as `${FIREBASE_PROJECT}` for
project identifiers and keep service-account material outside source control.

## License

Copyright (C) 2026 zandaulion and contributors.

This project is licensed under the GNU General Public License, version 3 only.
See [LICENSE](LICENSE).
