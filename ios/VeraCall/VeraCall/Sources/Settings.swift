//
//  Settings.swift
//  VeraCall
//
//  Where the Mac lives + the shared secret, persisted in UserDefaults. The phone
//  reaches the Mac directly over the Tailscale/WireGuard tunnel, so `host` is the
//  Mac's tailnet hostname (e.g. vera-mac.tailnet.ts.net) or its 100.x.y.z tailnet IP
//  — NOT a public address. No STUN/TURN is involved; the tunnel is the transport.
//
//  `port` defaults to 8766 to match anima/call_server.py (env ANIMA_CALL_PORT).
//  `authToken` is the Mac's ANIMA_TOKEN; it is sent as `Authorization: Bearer <token>`
//  on the /webrtc_offer POST. The call_server's _offer() currently does not enforce it
//  (see its phase-2 TODO), but anima/server.py's /device endpoint DOES require it, so we
//  keep one token field for both. Leave blank only if the Mac has ANIMA_TOKEN unset.
//

import Foundation
import Combine

final class VeraSettings: ObservableObject {
    private enum Key {
        static let host = "vera.host"
        static let port = "vera.port"
        static let token = "vera.authToken"
        static let mode = "vera.mode"
    }

    /// Mac's tailnet hostname or 100.x tailnet IP. Placeholder until the user sets theirs.
    @Published var host: String {
        didSet { UserDefaults.standard.set(host, forKey: Key.host) }
    }

    /// Call server port. Matches ANIMA_CALL_PORT (default 8766).
    @Published var port: Int {
        didSet { UserDefaults.standard.set(port, forKey: Key.port) }
    }

    /// Mac's ANIMA_TOKEN. Sent as a Bearer token on the offer POST. May be empty.
    @Published var authToken: String {
        didSet { UserDefaults.standard.set(authToken, forKey: Key.token) }
    }

    /// "loop" = talk to Vera (default), "echo" = bounce your own mic back (audio test).
    @Published var mode: String {
        didSet { UserDefaults.standard.set(mode, forKey: Key.mode) }
    }

    init() {
        let d = UserDefaults.standard
        self.host = d.string(forKey: Key.host) ?? "vera-mac.tailnet.ts.net"
        let p = d.integer(forKey: Key.port)
        self.port = p == 0 ? 8766 : p
        self.authToken = d.string(forKey: Key.token) ?? ""
        self.mode = d.string(forKey: Key.mode) ?? "loop"
    }

    /// The full offer URL, including the ?mode= query the call_server reads.
    /// Mirrors call_server's GET /calltest handshake: POST {sdp,type} -> {sdp,type}.
    var offerURL: URL? {
        var c = URLComponents()
        c.scheme = "http"            // plain HTTP is fine: the tunnel itself is encrypted.
        c.host = host
        c.port = port
        c.path = "/webrtc_offer"
        c.queryItems = [URLQueryItem(name: "mode", value: mode)]
        return c.url
    }

    var isConfigured: Bool {
        !host.trimmingCharacters(in: .whitespaces).isEmpty && port > 0
    }
}
