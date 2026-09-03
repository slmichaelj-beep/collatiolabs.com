//
//  VeraCallApp.swift
//  VeraCall
//
//  App entry point. Wires the SwiftUI scene to the AppDelegate, which owns the
//  long-lived singletons (CallKit provider, PushKit registry, the WebRTC client).
//  Those have to live at app scope, not view scope, because iOS may launch the app
//  straight into the background to deliver a VoIP push with no UI on screen at all.
//

import SwiftUI

@main
struct VeraCallApp: App {
    // UIApplicationDelegateAdaptor keeps the delegate alive for the whole process,
    // including background launches triggered by an incoming VoIP push.
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appDelegate.callController)
                .environmentObject(appDelegate.settings)
        }
    }
}
