plugins {
    id("com.android.library")
}

android {
    namespace = "dev.store.screenshots"
    compileSdk = 37

    defaultConfig {
        minSdk = 23
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    api("androidx.test:core:1.6.1")
    api("androidx.test.uiautomator:uiautomator:2.3.0")
}
