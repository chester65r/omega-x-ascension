FROM eclipse-temurin:17-jdk

ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
ENV GRADLE_USER_HOME=/opt/gradle-home
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools

# Install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    unzip wget git python3 \
    && rm -rf /var/lib/apt/lists/*

# Download and install Android command-line tools
RUN mkdir -p /opt/android-sdk/cmdline-tools && \
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline-tools.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /opt/android-sdk/cmdline-tools && \
    mv /opt/android-sdk/cmdline-tools/cmdline-tools /opt/android-sdk/cmdline-tools/latest && \
    rm /tmp/cmdline-tools.zip

# Accept licenses and install SDK components
RUN yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses > /dev/null 2>&1 || true
RUN /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager \
    "platform-tools" \
    "platforms;android-34" \
    "build-tools;34.0.0"

# Install Gradle
RUN wget -q https://services.gradle.org/distributions/gradle-8.1-bin.zip -O /tmp/gradle.zip && \
    unzip -q /tmp/gradle.zip -d /opt && \
    mv /opt/gradle-8.1 /opt/gradle && \
    rm /tmp/gradle.zip
ENV PATH=$PATH:/opt/gradle/bin

WORKDIR /project

# Copy project files
COPY . /project/

# Copy static dashboard to assets and build
RUN chmod +x build-apk.sh && \
    mkdir -p app/src/main/assets/web && \
    cp /project/../omega-x-ascension/static/style.css app/src/main/assets/web/ && \
    cp /project/../omega-x-ascension/static/app.js app/src/main/assets/web/ && \
    cp /project/../omega-x-ascension/static/icon-192.png app/src/main/assets/web/ && \
    cp /project/../omega-x-ascension/static/icon-512.png app/src/main/assets/web/ && \
    cp /project/../omega-x-ascension/static/favicon.png app/src/main/assets/web/ && \
    cp /project/../omega-x-ascension/static/apple-touch-icon.png app/src/main/assets/web/ && \
    python3 -c "
import re
with open('/project/../omega-x-ascension/static/index.html') as f:
    html = f.read()
html = html.replace('/static/', '')
html = re.sub(r'<link rel=\"manifest\"[^>]*>\n?', '', html)
html = re.sub(r'<script>\s*if \(.*serviceWorker.*\}</script>', '', html, flags=re.DOTALL)
with open('app/src/main/assets/web/index.html', 'w') as f:
    f.write(html)
" && \
    gradle wrapper --gradle-version 8.1 && \
    ./gradlew assembleDebug --no-daemon --stacktrace
