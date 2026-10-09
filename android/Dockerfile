FROM eclipse-temurin:17-jdk AS builder

ENV ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_HOME=/opt/android-sdk \
    GRADLE_USER_HOME=/opt/gradle-home \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
      unzip wget python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools" \
    && wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline-tools.zip \
    && unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_SDK_ROOT/cmdline-tools" \
    && mv "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools" "$ANDROID_SDK_ROOT/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip \
    && yes | sdkmanager --licenses >/dev/null 2>&1 || true

RUN sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

WORKDIR /repo
COPY android ./android
COPY omega-x-ascension/static ./omega-x-ascension/static
RUN chmod +x ./android/build-apk.sh ./android/gradlew && ./android/build-apk.sh

# Export with: docker build --target apk --output type=local,dest=dist -f android/Dockerfile .
FROM scratch AS apk
COPY --from=builder /repo/omega-x-ascension-0.5.0-debug.apk /
