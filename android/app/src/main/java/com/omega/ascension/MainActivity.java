package com.omega.ascension;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final String APP_URL =
            "https://appassets.androidplatform.net/assets/web/index.html";
    private static final String APP_ASSET_HOST = "appassets.androidplatform.net";
    private static final int REQUEST_RECORD_AUDIO = 4101;
    private static final int REQUEST_SPEECH = 4102;

    private WebView webView;
    private WebViewAssetLoader assetLoader;
    private TextToSpeech textToSpeech;
    private boolean textToSpeechReady = false;
    private String pendingSpeech = null;

    private static boolean isTrustedAppAsset(Uri uri) {
        String path = uri.getPath();
        return "https".equalsIgnoreCase(uri.getScheme())
                && APP_ASSET_HOST.equalsIgnoreCase(uri.getHost())
                && path != null
                && path.startsWith("/assets/");
    }

    private static boolean isTrustedAppOrigin(Uri uri) {
        return "https".equalsIgnoreCase(uri.getScheme())
                && APP_ASSET_HOST.equalsIgnoreCase(uri.getHost());
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        assetLoader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        webView = findViewById(R.id.webview);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }

        configureNativeMessageChannel();

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(
                    WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) {
                    return false;
                }

                Uri uri = request.getUrl();
                if (isTrustedAppAsset(uri)) {
                    return false;
                }

                // Keep untrusted pages out of the app's privileged top-level WebView.
                if ("https".equalsIgnoreCase(uri.getScheme())) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (ActivityNotFoundException ignored) {
                        // Keep the unsupported navigation blocked.
                    }
                }
                return true;
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(
                    WebView view, WebResourceRequest request) {
                return assetLoader.shouldInterceptRequest(request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
                return assetLoader.shouldInterceptRequest(Uri.parse(url));
            }
        });

        textToSpeech = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS && textToSpeech != null) {
                int languageStatus = textToSpeech.setLanguage(Locale.getDefault());
                textToSpeechReady = languageStatus != TextToSpeech.LANG_MISSING_DATA
                        && languageStatus != TextToSpeech.LANG_NOT_SUPPORTED;
                if (textToSpeechReady && pendingSpeech != null) {
                    String queued = pendingSpeech;
                    pendingSpeech = null;
                    speakText(queued);
                }
            } else {
                textToSpeechReady = false;
            }
        });

        if (savedInstanceState == null) {
            webView.loadUrl(APP_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void configureNativeMessageChannel() {
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            return;
        }

        WebViewCompat.addWebMessageListener(
                webView,
                "OmegaNative",
                Collections.singleton("https://" + APP_ASSET_HOST),
                (view, message, sourceOrigin, isMainFrame, replyProxy) -> {
                    if (!isMainFrame || !isTrustedAppOrigin(sourceOrigin)) {
                        return;
                    }
                    final String payload = message.getData();
                    runOnUiThread(() -> handleNativeMessage(payload));
                });
    }

    private void handleNativeMessage(String payload) {
        try {
            JSONObject message = new JSONObject(payload == null ? "{}" : payload);
            String action = message.optString("action", "");
            String text = message.optString("text", "");
            String url = message.optString("url", "");

            switch (action) {
                case "openBrowser":
                    openBrowser(url);
                    break;
                case "share":
                    shareText(text);
                    break;
                case "speak":
                    speakText(text);
                    break;
                case "voiceInput":
                    startVoiceInput();
                    break;
                case "haptic":
                    hapticFeedback();
                    break;
                case "deviceInfo":
                    String device = Build.MANUFACTURER + " " + Build.MODEL
                            + " · Android " + Build.VERSION.RELEASE
                            + " (API " + Build.VERSION.SDK_INT + ")";
                    dispatchNativeEvent("device-info", device);
                    break;
                default:
                    dispatchNativeEvent("native-error", "Unsupported Android action.");
                    break;
            }
        } catch (Exception ignored) {
            dispatchNativeEvent("native-error", "The Android action request was invalid.");
        }
    }

    private void openBrowser(String url) {
        Intent intent = new Intent(this, BrowserActivity.class);
        intent.putExtra(BrowserActivity.EXTRA_URL, url == null ? "" : url);
        startActivity(intent);
    }

    private void shareText(String value) {
        String text = value == null ? "" : value.trim();
        if (text.isEmpty()) {
            dispatchNativeEvent("native-error", "There is no text to share.");
            return;
        }
        Intent sendIntent = new Intent(Intent.ACTION_SEND);
        sendIntent.setType("text/plain");
        sendIntent.putExtra(Intent.EXTRA_TEXT, text.substring(0, Math.min(text.length(), 8000)));
        try {
            startActivity(Intent.createChooser(sendIntent, "Share from OMEGA-X"));
        } catch (ActivityNotFoundException ignored) {
            dispatchNativeEvent("native-error", "No compatible Android sharing app was found.");
        }
    }

    private void speakText(String value) {
        String text = value == null ? "" : value.trim();
        if (text.isEmpty()) {
            dispatchNativeEvent("native-error", "There is no answer to read aloud.");
            return;
        }
        pendingSpeech = text.substring(0, Math.min(text.length(), 4000));
        if (textToSpeechReady && textToSpeech != null) {
            String toRead = pendingSpeech;
            pendingSpeech = null;
            textToSpeech.speak(toRead, TextToSpeech.QUEUE_FLUSH, null, "omega-x-answer");
        } else if (textToSpeech == null) {
            dispatchNativeEvent("native-error", "Android text-to-speech is not initialized.");
        }
    }

    private void startVoiceInput() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQUEST_RECORD_AUDIO);
            return;
        }
        launchSpeechRecognizer();
    }

    private void launchSpeechRecognizer() {
        if (!android.speech.SpeechRecognizer.isRecognitionAvailable(this)) {
            dispatchNativeEvent("speech-error", "No Android speech recognition service is installed.");
            return;
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault());
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak your task for OMEGA-X");
        try {
            startActivityForResult(intent, REQUEST_SPEECH);
        } catch (ActivityNotFoundException ignored) {
            dispatchNativeEvent("speech-error", "The Android speech recognition activity could not be opened.");
        }
    }

    private void hapticFeedback() {
        try {
            Vibrator vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            if (vibrator == null || !vibrator.hasVibrator()) {
                return;
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createOneShot(
                        24, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                vibrator.vibrate(24);
            }
        } catch (SecurityException ignored) {
            // Haptic feedback is optional on devices that restrict it.
        }
    }

    private void dispatchNativeEvent(String action, String text) {
        if (webView == null) {
            return;
        }
        final String js = "window.dispatchEvent(new CustomEvent('omega:native',{detail:{action:"
                + JSONObject.quote(action) + ",text:" + JSONObject.quote(text == null ? "" : text)
                + "}}));";
        runOnUiThread(() -> {
            if (webView != null) {
                webView.evaluateJavascript(js, null);
            }
        });
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_RECORD_AUDIO) {
            return;
        }
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            launchSpeechRecognizer();
        } else {
            dispatchNativeEvent("speech-error", "Microphone permission was denied.");
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_SPEECH) {
            return;
        }
        if (resultCode != RESULT_OK || data == null) {
            dispatchNativeEvent("speech-error", "Speech input was cancelled or returned no result.");
            return;
        }
        ArrayList<String> matches = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
        if (matches == null || matches.isEmpty()) {
            dispatchNativeEvent("speech-error", "No speech was recognized.");
            return;
        }
        dispatchNativeEvent("speech-result", matches.get(0));
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) {
            webView.saveState(outState);
        }
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        if (textToSpeech != null) {
            textToSpeech.stop();
            textToSpeech.shutdown();
            textToSpeech = null;
        }
        super.onDestroy();
    }
}
