package com.omega.ascension;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.webkit.WebView;
import android.webkit.WebSettings;
import android.webkit.WebViewClient;
import android.widget.EditText;

public class MainActivity extends Activity {

    private WebView webView;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences("omega", MODE_PRIVATE);
        webView = findViewById(R.id.webview);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                String apiBase = prefs.getString("api_base", "http://localhost:3000");
                view.evaluateJavascript(
                    "window.__API_BASE__ = '" + apiBase + "';" +
                    "const _fetch = window.fetch;" +
                    "window.fetch = function(input, init) {" +
                    "  if (typeof input === 'string' && input.startsWith('/') && !input.startsWith('//')) {" +
                    "    input = window.__API_BASE__ + input;" +
                    "  }" +
                    "  return _fetch.call(this, input, init);" +
                    "};",
                    null
                );
            }
        });

        // Long-press the WebView to open server settings
        webView.setOnLongClickListener(v -> {
            showServerSettings();
            return true;
        });

        webView.loadUrl("file:///android_asset/web/index.html");
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    public void showServerSettings() {
        String current = prefs.getString("api_base", "http://localhost:3000");
        final EditText input = new EditText(this);
        input.setText(current);
        new AlertDialog.Builder(this)
            .setTitle("Server URL")
            .setMessage("Enter the OMEGA-X API server URL")
            .setView(input)
            .setPositiveButton("Save", (d, w) -> {
                String url = input.getText().toString().trim().replaceAll("/$", "");
                prefs.edit().putString("api_base", url).apply();
                webView.loadUrl("file:///android_asset/web/index.html");
            })
            .setNegativeButton("Cancel", null)
            .show();
    }
}
