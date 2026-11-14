#import <Foundation/Foundation.h>
#import <WebKit/WebKit.h>
#import <objc/runtime.h>

void SetupWebViewInjection(WKWebView *webView) {
    WKUserScript *script = [[WKUserScript alloc] initWithSource:@"console.log('injected');"
                                                  injectionTime:WKUserScriptInjectionTimeAtDocumentStart
                                               forMainFrameOnly:NO];
    [webView.configuration.userContentController addUserScript:script];
}

void SwizzleInit(Class cls, SEL orig, SEL alt) {
    Method origMethod = class_getInstanceMethod(cls, orig);
    Method altMethod = class_getInstanceMethod(cls, alt);
    method_exchangeImplementations(origMethod, altMethod);
}
