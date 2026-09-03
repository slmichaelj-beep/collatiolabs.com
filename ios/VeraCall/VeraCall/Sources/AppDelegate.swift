//
//  AppDelegate.swift
//  VeraCall
//
//  Owns the app-scoped singletons and the PushKit VoIP registry. iOS can launch this
//  app straight into the background to deliver a VoIP push (even from a terminated
//  state), so registration must happen at launch, unconditionally.
//
//  PushKit contract (iOS 13+): when a .voIP push arrives you MUST report an incoming
//  call to CallKit *synchronously* inside didReceiveIncomingPushWith, and only call the
//  completion handler afterwards. Failing to do so gets your app killed and, after a few
//  offenses, your VoIP pushes throttled. We satisfy this by calling
//  CallController.reportIncomingCall(...) and forwarding its completion.
//

import UIKit
import PushKit
import CallKit
import WebRTC
import os.log

final class AppDelegate: NSObject, UIApplicationDelegate {

    let settings = VeraSettings()
    lazy var callController: CallController = {
        let c = CallController()
        c.settings = settings
        return c
    }()

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "app")
    private var voipRegistry: PKPushRegistry?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // WebRTC global init, once per process.
        RTCInitializeSSL()
        // Let RTCAudioSession cooperate with CallKit instead of auto-configuring.
        RTCAudioSession.sharedInstance().useManualAudio = true
        RTCAudioSession.sharedInstance().isAudioEnabled = false

        registerForVoIPPushes()
        return true
    }

    func applicationWillTerminate(_ application: UIApplication) {
        RTCCleanupSSL()
    }

    // MARK: - PushKit registration

    private func registerForVoIPPushes() {
        let registry = PKPushRegistry(queue: .main)
        registry.delegate = self
        registry.desiredPushTypes = [.voIP]
        self.voipRegistry = registry
        log.info("registered for VoIP pushes")
    }
}

// MARK: - PKPushRegistryDelegate

extension AppDelegate: PKPushRegistryDelegate {

    /// The VoIP token. This is the token the Mac must send the push TO. Register it with
    /// the Mac by POSTing {"voip_token": "<hex>", "platform": "ios", "bundle_id": "..."}
    /// to anima/server.py's /device endpoint (Bearer ANIMA_TOKEN). See README.
    func pushRegistry(_ registry: PKPushRegistry,
                      didUpdate pushCredentials: PKPushCredentials,
                      for type: PKPushType) {
        guard type == .voIP else { return }
        let token = pushCredentials.token.map { String(format: "%02x", $0) }.joined()
        log.info("VoIP push token: \(token, privacy: .public)")
        // Surface it to the UI (Settings screen shows + copies it) and try to auto-register.
        NotificationCenter.default.post(name: .veraDidUpdateVoIPToken,
                                        object: nil,
                                        userInfo: ["token": token])
        DeviceRegistration.register(voipToken: token, settings: settings)
    }

    func pushRegistry(_ registry: PKPushRegistry,
                      didInvalidatePushTokenFor type: PKPushType) {
        guard type == .voIP else { return }
        log.info("VoIP push token invalidated")
    }

    /// An incoming VoIP push. Report the call to CallKit synchronously, then complete.
    func pushRegistry(_ registry: PKPushRegistry,
                      didReceiveIncomingPushWith payload: PKPushPayload,
                      for type: PKPushType,
                      completion: @escaping () -> Void) {
        guard type == .voIP else { completion(); return }

        // Expected payload shape (documented in voip_push.py and the README):
        // {
        //   "aps": { "alert": "Vera is calling", "sound": "default" },   // optional
        //   "handle": "Vera",                                            // caller label
        //   "call_uuid": "EAB3...-...."                                  // optional, agreed id
        // }
        let dict = payload.dictionaryPayload
        let handle = (dict["handle"] as? String) ?? "Vera"
        let callID: UUID = {
            if let s = dict["call_uuid"] as? String, let u = UUID(uuidString: s) { return u }
            return UUID()
        }()

        log.info("incoming VoIP push -> reporting call \(callID.uuidString, privacy: .public)")
        callController.reportIncomingCall(callID: callID, handle: handle, completion: completion)
    }
}

extension Notification.Name {
    /// Posted when the VoIP token changes, so the Settings screen can display/copy it.
    static let veraDidUpdateVoIPToken = Notification.Name("veraDidUpdateVoIPToken")
}
