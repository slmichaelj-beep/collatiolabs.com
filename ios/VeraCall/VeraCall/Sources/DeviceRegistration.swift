//
//  DeviceRegistration.swift
//  VeraCall
//
//  Tells the Mac where to send VoIP pushes, by POSTing the phone's PushKit token to
//  anima/server.py's existing /device endpoint. We do NOT modify server.py; we just
//  speak its protocol.
//
//  IMPORTANT: /device lives on the MAIN anima server (default port 8765), NOT on the
//  call server (8766). It is gated behind ANIMA_TOKEN (sent as Authorization: Bearer).
//  _store_device() accepts: {"token": <apns alert token>, "voip_token": <pushkit token>,
//  "platform": "ios", "bundle_id": "..."} and stores it under .anima/<name>.device.json.
//  Vera's reminder/call subsystem then reads voip_token to ring this phone.
//
//  The main-server port is derived from the call port the user configured: call server
//  default 8766 -> main server default 8765. If your setup differs, change MAIN_PORT.
//

import Foundation
import os.log

enum DeviceRegistration {

    /// The main anima server port. The call server is 8766; the brain/server is 8765.
    /// If you run the main server on a non-default port, set it here.
    static let mainServerPort = 8765

    private static let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "register")

    /// POST the VoIP token to the Mac's /device endpoint. Best-effort: failures are logged,
    /// not surfaced, because the user can always copy the token from Settings and register
    /// it by hand (curl) per the README.
    static func register(voipToken: String, settings: VeraSettings) {
        guard settings.isConfigured else { return }

        var c = URLComponents()
        c.scheme = "http"
        c.host = settings.host
        c.port = mainServerPort
        c.path = "/device"
        guard let url = c.url else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !settings.authToken.isEmpty {
            request.setValue("Bearer \(settings.authToken)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 15

        let bundleID = Bundle.main.bundleIdentifier ?? ""
        let body: [String: String] = [
            "voip_token": voipToken,
            "platform": "ios",
            "bundle_id": bundleID
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        request.httpBody = data

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                log.error("device registration failed: \(error.localizedDescription)")
                return
            }
            if let http = response as? HTTPURLResponse {
                log.info("device registration -> HTTP \(http.statusCode)")
            }
        }.resume()
    }
}
