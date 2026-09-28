// SPDX-License-Identifier: GPL-3.0-only
package dev.store.screenshots;

import android.app.Instrumentation;

import androidx.annotation.NonNull;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;

import java.io.File;
import java.util.Objects;
import java.util.regex.Pattern;

/** Generic UI Automator operations shared by Play Store screenshot tests. */
public final class ScreenshotRobot {
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]*");

    private final UiDevice device;
    private final File outputDirectory;
    private final long defaultTimeoutMillis;
    private final long idleTimeoutMillis;

    public ScreenshotRobot(
            @NonNull UiDevice device,
            @NonNull File outputDirectory,
            long defaultTimeoutMillis,
            long idleTimeoutMillis
    ) {
        this.device = device;
        this.outputDirectory = outputDirectory;
        this.defaultTimeoutMillis = defaultTimeoutMillis;
        this.idleTimeoutMillis = idleTimeoutMillis;
    }

    public void lockPortrait() throws Exception {
        device.setOrientationPortrait();
        waitForIdle();
    }

    public void releaseOrientation() throws Exception {
        device.unfreezeRotation();
    }

    @NonNull
    public UiObject2 waitForText(@NonNull String text) {
        return waitForText(text, false);
    }

    @NonNull
    public UiObject2 waitForText(@NonNull String text, boolean substring) {
        UiObject2 object = device.wait(
                Until.findObject(substring ? By.textContains(text) : By.text(text)),
                defaultTimeoutMillis
        );
        if (object == null) {
            throw new IllegalStateException("Timed out waiting for text '" + text + "'");
        }
        waitForIdle();
        return object;
    }

    @NonNull
    public UiObject2 waitForDescription(@NonNull String description) {
        UiObject2 object = device.wait(
                Until.findObject(By.desc(description)),
                defaultTimeoutMillis
        );
        if (object == null) {
            throw new IllegalStateException(
                    "Timed out waiting for content description '" + description + "'"
            );
        }
        waitForIdle();
        return object;
    }

    public void tapText(@NonNull String text) {
        tapText(text, false);
    }

    public void tapText(@NonNull String text, boolean substring) {
        waitForText(text, substring).click();
        waitForIdle();
    }

    public void tapDescription(@NonNull String description) {
        waitForDescription(description).click();
        waitForIdle();
    }

    public boolean dismissSystemDialog(
            @NonNull String title,
            @NonNull String action,
            long timeoutMillis
    ) {
        if (!device.wait(Until.hasObject(By.text(title)), timeoutMillis)) {
            return false;
        }
        UiObject2 button = device.wait(Until.findObject(By.text(action)), timeoutMillis);
        if (button == null) {
            throw new IllegalStateException(
                    "Found system dialog '" + title + "' but not action '" + action + "'"
            );
        }
        button.click();
        waitForIdle();
        return true;
    }

    @NonNull
    public File capture(@NonNull String name) {
        if (!SAFE_NAME.matcher(name).matches()) {
            throw new IllegalArgumentException("Screenshot name must be filesystem-safe: " + name);
        }
        waitForIdle();
        if (!outputDirectory.exists() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("Could not create " + outputDirectory);
        }
        File destination = new File(outputDirectory, name + ".png");
        if (!device.takeScreenshot(destination)) {
            throw new IllegalStateException("Could not capture " + destination);
        }
        return destination;
    }

    public void pressBack() {
        device.pressBack();
        waitForIdle();
    }

    private void waitForIdle() {
        device.waitForIdle(idleTimeoutMillis);
    }

    @NonNull
    public static ScreenshotRobot fromInstrumentation(@NonNull Instrumentation instrumentation) {
        return fromInstrumentation(instrumentation, "screenshots");
    }

    @NonNull
    public static ScreenshotRobot fromInstrumentation(
            @NonNull Instrumentation instrumentation,
            @NonNull String directoryName
    ) {
        File external = Objects.requireNonNull(
                instrumentation.getTargetContext().getExternalFilesDir(null),
                "App-scoped external files directory is unavailable"
        );
        return new ScreenshotRobot(
                UiDevice.getInstance(instrumentation),
                new File(external, directoryName),
                30_000,
                1_000
        );
    }
}
