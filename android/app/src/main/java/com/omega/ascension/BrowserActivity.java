package com.omega.ascension;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.net.URLEncoder;

public class BrowserActivity extends Activity {
    public static final String EXTRA_URL = "com.omega.ascension.extra.BROWSER_URL";

    private static final int BG = Color.rgb(5, 5, 5);
    private static final int PANEL = Color.rgb(17, 17, 17);
    private static final int EDGE = Color.rgb(58, 58, 58);
    private static final int FG = Color.rgb(245, 245, 245);
    private static final int MUTED = Color.rgb(160, 160, 160);
    private static final String SEARCH = "https://html.duckduckgo.com/html/?q=";

    private WebView browser;
    private EditText address;
    private ProgressBar progress;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(createLayout());
        configureBrowser();

        String initial = getIntent() == null ? "" : getIntent().getStringExtra(EXTRA_URL);
        openAddress(initial == null || initial.trim().isEmpty()
                ? "https://duckduckgo.com/" : initial);
    }

    private View createLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        root.setFocusableInTouchMode(true);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(16), dp(5), dp(10), dp(5));
        header.setBackgroundColor(BG);

        TextView brand = new TextView(this);
        brand.setText("OMEGA-X  /  BROWSER");
        brand.setTextColor(FG);
        brand.setTextSize(12);
        brand.setLetterSpacing(0.06f);
        brand.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(brand, new LinearLayout.LayoutParams(0, dp(44), 1f));

        Button close = makeButton("Close");
        close.setContentDescription("Close internal browser");
        close.setOnClickListener(v -> finish());
        header.addView(close, new LinearLayout.LayoutParams(dp(70), dp(40)));
        root.addView(header, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(52)));

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(8), dp(3), dp(8), dp(6));
        toolbar.setBackgroundColor(BG);

        Button back = makeButton("‹");
        back.setContentDescription("Go back");
        back.setTextSize(22);
        back.setOnClickListener(v -> {
            if (browser.canGoBack()) browser.goBack();
        });
        toolbar.addView(back, new LinearLayout.LayoutParams(dp(42), dp(42)));

        Button forward = makeButton("›");
        forward.setContentDescription("Go forward");
        forward.setTextSize(22);
        forward.setOnClickListener(v -> {
            if (browser.canGoForward()) browser.goForward();
        });
        LinearLayout.LayoutParams arrowParams = new LinearLayout.LayoutParams(dp(42), dp(42));
        arrowParams.leftMargin = dp(4);
        toolbar.addView(forward, arrowParams);

        Button reload = makeButton("↻");
        reload.setContentDescription("Reload page");
        reload.setTextSize(18);
        reload.setOnClickListener(v -> browser.reload());
        LinearLayout.LayoutParams reloadParams = new LinearLayout.LayoutParams(dp(42), dp(42));
        reloadParams.leftMargin = dp(4);
        toolbar.addView(reload, reloadParams);

        address = new EditText(this);
        address.setId(R.id.native_browser_address);
        address.setSingleLine(true);
        address.setTextSize(13);
        address.setTextColor(FG);
        address.setHintTextColor(MUTED);
        address.setHint("Enter a URL or search");
        address.setSelectAllOnFocus(false);
        address.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        address.setImeOptions(EditorInfo.IME_ACTION_GO);
        address.setPadding(dp(10), 0, dp(8), 0);
        address.setBackgroundTintList(android.content.res.ColorStateList.valueOf(EDGE));
        LinearLayout.LayoutParams addressParams =
                new LinearLayout.LayoutParams(0, dp(42), 1f);
        addressParams.leftMargin = dp(6);
        toolbar.addView(address, addressParams);

        Button go = makeButton("Go");
        go.setContentDescription("Open URL or search");
        go.setOnClickListener(v -> openAddress(address.getText().toString()));
        LinearLayout.LayoutParams goParams = new LinearLayout.LayoutParams(dp(54), dp(42));
        goParams.leftMargin = dp(6);
        toolbar.addView(go, goParams);

        address.setOnEditorActionListener((view, actionId, event) -> {
            boolean enter = event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER
                    && event.getAction() == KeyEvent.ACTION_DOWN;
            if (actionId == EditorInfo.IME_ACTION_GO || enter) {
                InputMethodManager manager =
                        (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                if (manager != null) {
                    manager.hideSoftInputFromWindow(address.getWindowToken(), 0);
                }
                openAddress(address.getText().toString());
                return true;
            }
            return false;
        });
        root.addView(toolbar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(54)));

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(FG));
        progress.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(PANEL));
        root.addView(progress, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(2)));

        browser = new WebView(this);
        browser.setId(R.id.native_browser_webview);
        root.addView(browser, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        return root;
    }

    private Button makeButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setTextColor(FG);
        button.setTextSize(12);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(5), 0, dp(5), 0);
        button.setBackgroundTintList(android.content.res.ColorStateList.valueOf(PANEL));
        button.setMinHeight(dp(40));
        button.setMinimumHeight(dp(40));
        return button;
    }

    private void configureBrowser() {
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSaveFormData(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }

        browser.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleNavigation(view, request.getUrl());
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleNavigation(view, Uri.parse(url));
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                Uri uri = Uri.parse(url);
                if (isWebScheme(uri) && address != null && !address.hasFocus()) {
                    address.setText(url);
                    address.setSelection(address.length());
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (progress != null) {
                    progress.setProgress(100);
                    progress.setVisibility(View.GONE);
                }
            }
        });

        browser.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });
    }

    private boolean handleNavigation(WebView view, Uri uri) {
        if (isWebScheme(uri)) {
            if ("http".equalsIgnoreCase(uri.getScheme()) && !isLoopback(uri.getHost())) {
                Uri secureUri = uri.buildUpon().scheme("https").build();
                view.loadUrl(secureUri.toString());
                return true;
            }
            return false;
        }

        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        if ("mailto".equals(scheme) || "tel".equals(scheme)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (ActivityNotFoundException ignored) {
                Toast.makeText(this, "No compatible app is installed for this link.", Toast.LENGTH_SHORT).show();
            }
        }
        // Do not allow file:, content:, intent:, javascript:, or other custom schemes here.
        return true;
    }

    private static boolean isWebScheme(Uri uri) {
        String scheme = uri.getScheme();
        return ("https".equalsIgnoreCase(scheme) || "http".equalsIgnoreCase(scheme))
                && uri.getHost() != null
                && !uri.getHost().isEmpty()
                && uri.getUserInfo() == null;
    }

    private static boolean isLoopback(String host) {
        if (host == null) return false;
        return "localhost".equalsIgnoreCase(host)
                || "127.0.0.1".equals(host)
                || "::1".equals(host)
                || "[::1]".equalsIgnoreCase(host);
    }

    private String normalizeAddress(String value) {
        String raw = value == null ? "" : value.trim();
        if (raw.isEmpty()) return "https://duckduckgo.com/";

        String candidate;
        if (raw.matches("(?i)^https?://.*")) {
            candidate = raw;
        } else if (raw.matches("(?i)^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::\\d{1,5})?(?:/[^\\s]*)?$")
                && raw.contains(".")) {
            candidate = "https://" + raw;
        } else {
            try {
                candidate = SEARCH + URLEncoder.encode(raw, "UTF-8");
            } catch (Exception ignored) {
                candidate = "https://duckduckgo.com/";
            }
        }

        Uri parsed = Uri.parse(candidate);
        if (!isWebScheme(parsed)) {
            throw new IllegalArgumentException("Enter a valid HTTPS URL or a search query.");
        }
        if ("http".equalsIgnoreCase(parsed.getScheme()) && !isLoopback(parsed.getHost())) {
            candidate = parsed.buildUpon().scheme("https").build().toString();
        }
        return candidate;
    }

    private void openAddress(String value) {
        try {
            String target = normalizeAddress(value);
            address.setText(target);
            address.setSelection(address.length());
            progress.setVisibility(View.VISIBLE);
            progress.setProgress(0);
            browser.loadUrl(target);
        } catch (IllegalArgumentException error) {
            Toast.makeText(this, error.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    public void onBackPressed() {
        if (browser != null && browser.canGoBack()) {
            browser.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        if (browser != null) browser.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (browser != null) browser.onResume();
    }

    @Override
    protected void onDestroy() {
        if (browser != null) {
            browser.stopLoading();
            browser.removeAllViews();
            browser.destroy();
            browser = null;
        }
        super.onDestroy();
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
