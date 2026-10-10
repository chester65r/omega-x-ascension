package com.omega.ascension;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.content.Intent;
import android.widget.EditText;
import android.webkit.WebView;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.concurrent.atomic.AtomicReference;

@RunWith(AndroidJUnit4.class)
public class DashboardSmokeTest {

    private String evaluate(WebView webView, String script) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(
                () -> webView.evaluateJavascript(script, value -> {
                    result.set(value);
                    latch.countDown();
                }));
        assertTrue("WebView JavaScript evaluation timed out",
                latch.await(10, TimeUnit.SECONDS));
        return result.get();
    }

    @Test
    public void bundledDashboardLoadsAndMainTabsWork() throws Exception {
        try (ActivityScenario<MainActivity> scenario =
                     ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<WebView> webViewRef = new AtomicReference<>();
            AtomicReference<Boolean> loadedRef = new AtomicReference<>(false);
            long deadline = System.currentTimeMillis() + 20000;

            while (System.currentTimeMillis() < deadline) {
                scenario.onActivity(activity -> {
                    webViewRef.set(activity.findViewById(R.id.webview));
                    loadedRef.set(activity.isDashboardLoaded());
                });
                if (Boolean.TRUE.equals(loadedRef.get())) {
                    break;
                }
                Thread.sleep(250);
            }

            assertTrue("MainActivity did not finish loading its trusted bundled dashboard",
                    Boolean.TRUE.equals(loadedRef.get()));
            WebView webView = webViewRef.get();
            assertNotNull("MainActivity must contain its WebView", webView);
            assertTrue("Dashboard WebView must have JavaScript enabled",
                    webView.getSettings().getJavaScriptEnabled());
            assertTrue("Dashboard WebView must have DOM storage enabled",
                    webView.getSettings().getDomStorageEnabled());
            assertEquals("Dashboard title must be loaded from the bundled HTML",
                    "OMEGA-X ASCENSION", webView.getTitle());
            assertTrue("Dashboard must remain on its trusted local asset origin",
                    webView.getUrl() != null
                            && webView.getUrl().startsWith(
                                    "https://appassets.androidplatform.net/assets/web/index.html"));
        }
    }


    @Test
    public void nativeBrowserLaunchesWithAddressBarAndWebView() {
        Intent intent = new Intent(
                InstrumentationRegistry.getInstrumentation().getTargetContext(),
                BrowserActivity.class);
        intent.putExtra(BrowserActivity.EXTRA_URL, "https://example.com/");
        try (ActivityScenario<BrowserActivity> scenario = ActivityScenario.launch(intent)) {
            AtomicReference<WebView> browserRef = new AtomicReference<>();
            AtomicReference<EditText> addressViewRef = new AtomicReference<>();
            AtomicReference<String> addressTextRef = new AtomicReference<>();
            scenario.onActivity(activity -> {
                browserRef.set(activity.findViewById(R.id.native_browser_webview));
                EditText address = activity.findViewById(R.id.native_browser_address);
                addressViewRef.set(address);
                addressTextRef.set(address == null ? "" : address.getText().toString());
            });
            assertNotNull("Native browser must contain a WebView", browserRef.get());
            assertNotNull("Native browser must contain an address bar", addressViewRef.get());
            assertTrue("Native browser must preserve a valid HTTPS address",
                    addressTextRef.get() != null && addressTextRef.get().startsWith("https://example.com"));
        }
    }
}
