// SPDX-License-Identifier: GPL-3.0-only
package com.example.app

import android.content.Context
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.store.screenshots.ScreenshotRobot
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * App-specific adapter for the reusable screenshot harness.
 *
 * WARNING: fixture setup may delete application data. Run this only on a
 * disposable emulator or Firebase Test Lab device.
 */
@RunWith(AndroidJUnit4::class)
class PlayStoreScreenshotTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val targetContext: Context get() = instrumentation.targetContext
    private lateinit var scenario: ActivityScenario<MainActivity>
    private lateinit var robot: ScreenshotRobot

    @Before
    fun seedAndLaunch() {
        // Replace with deterministic app-specific fixture setup before launch.
        seedScreenshotData(targetContext)
        robot = ScreenshotRobot.fromInstrumentation(instrumentation)
        robot.lockPortrait()
        scenario = ActivityScenario.launch(MainActivity::class.java)
        robot.dismissSystemDialog("Android App Compatibility", "Don't Show Again", 5_000)
        robot.waitForText("Unique home-screen heading")
    }

    @After
    fun close() {
        if (::scenario.isInitialized) scenario.close()
        if (::robot.isInitialized) robot.releaseOrientation()
    }

    @Test
    fun capturePlayStoreScreens() {
        robot.capture("01-home")

        robot.tapDescription("Second destination")
        robot.waitForText("Unique second-screen heading")
        robot.capture("02-second-screen")
    }

    private fun seedScreenshotData(context: Context) {
        // Insert local fixtures, select a stable theme, and set cache timestamps.
    }
}
