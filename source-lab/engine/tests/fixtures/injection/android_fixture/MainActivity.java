package com.test.injection;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebView;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView webView = new WebView(this);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setAllowUniversalAccessFromFileURLs(true);
        webView.addJavascriptInterface(new BridgeObject(), "nativeBridge");
        webView.loadUrl("https://example.test");
    }

    class BridgeObject {
        @android.webkit.JavascriptInterface
        public String execute(String cmd) {
            return "executed:" + cmd;
        }
    }
}
