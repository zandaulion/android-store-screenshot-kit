# Integrating an Android application

## What belongs where

The shared repository owns Firebase submission, result discovery, downloads,
validation, APK alignment checks, and generic UI Automator operations.

The application repository owns:

- deterministic fixture data;
- database, authentication, or onboarding setup;
- the sequence of screens to capture;
- selectors that identify its controls and ready states;
- screenshot captions and store metadata.

Do not put production credentials into screenshot fixtures. Prefer a disposable
Test Lab device and recorded data that exercises the same local code path the
application normally uses.

## Add the harness as a local Gradle project

One convenient layout is a Git submodule:

```text
your-app/
├── app/
├── screenshot-kit.toml
└── tools/android-store-screenshot-kit/
```

Add the harness module to `settings.gradle.kts`:

```kotlin
include(":store-screenshot-harness")
project(":store-screenshot-harness").projectDir =
    file("tools/android-store-screenshot-kit/harness")
```

Then add it only to the application test configuration:

```kotlin
dependencies {
    androidTestImplementation(project(":store-screenshot-harness"))
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}
```

Set `testInstrumentationRunner` if the application does not already have one:

```kotlin
android {
    defaultConfig {
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
}
```

The harness uses only AndroidX Test and UI Automator. It does not depend on
Compose, Espresso, the app's database, or the app's architecture.

## Stage deterministic fixture assets

If the screenshots should exercise the production cache/model path, stage
recorded fixtures into the test APK instead of teaching the test to contact a
live service. One Gradle pattern is:

```kotlin
import org.gradle.api.tasks.Sync

val screenshotFixturesDir = layout.buildDirectory.dir("generated/screenshotFixtures")
val stageScreenshotFixtures = tasks.register<Sync>("stageScreenshotFixtures") {
    from(rootProject.file("../fixtures")) {
        include("*.model.json")
    }
    into(screenshotFixturesDir)
}

android {
    sourceSets.getByName("androidTest") {
        assets.srcDir(screenshotFixturesDir.get().asFile)
    }
}

tasks.matching { it.name == "mergeDebugAndroidTestAssets" }.configureEach {
    dependsOn(stageScreenshotFixtures)
}
```

The instrumentation context reads assets from the test APK; the target context
opens the application's files and database. Keep those two contexts distinct.

## Write the app adapter

Start with `templates/PlayStoreScreenshotTest.kt`. Its setup deliberately
contains placeholders: only the app knows how to create a stable account state,
seed Room, stage cached models, or bypass an onboarding screen intended for
real users.

Use accessibility descriptions for icon-only navigation and unique visible text
for ready states. A text label that occurs on two screens is not a safe signal
that a transition has finished.

Write screenshots to the app-scoped external directory returned by
`Context.getExternalFilesDir(null)`. The config's `remote_directory` must point
to the same directory so Firebase Test Lab pulls it into the result artifacts.

Instrumentation setup may delete the target application's database. Keep that
behavior conspicuous in code and run destructive fixture setup only on disposable
emulators or Test Lab devices.

## Configure Test Lab

Copy `examples/screenshot-kit.toml` into the application repository. Keep cloud
project identifiers in environment variables. Device availability changes, so
query the catalog before adopting an axis:

```bash
gcloud firebase test android models list
```

Start with a virtual device. Add a physical device after the flow is stable.
The runner always requires an explicit `--device` selection and therefore does
not silently run every configured, potentially billed, axis.

One Firebase/GCP project can run APKs from multiple Android projects. Use a
distinct `history_name` per product so results remain navigable.

## CI

In CI, authenticate `gcloud` through the platform's short-lived identity
mechanism where possible. Store neither service-account JSON nor access tokens
in this repository. Run virtual devices on ordinary pull requests and reserve
physical devices for release candidates or manually approved workflows.
