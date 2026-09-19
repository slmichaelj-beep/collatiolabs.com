//
//  WebRTCClient.swift
//  VeraCall
//
//  The audio-only WebRTC peer. This is the Swift twin of the JS in call_server.py's
//  GET /calltest page. The handshake is intentionally minimal (no trickle ICE, no
//  data channel): create an offer, POST it to the Mac, apply the returned answer.
//
//  Exact handshake (must match anima/call_server.py::_offer):
//    1. getUserMedia(audio) -> add a local mic audio track
//    2. createOffer / setLocalDescription
//    3. POST {"sdp": localSDP, "type": "offer"}  to  http://<mac>:8766/webrtc_offer?mode=loop
//    4. response is {"sdp": answerSDP, "type": "answer"}
//    5. setRemoteDescription(answer)
//    6. her audio arrives on the remote track -> play it
//
//  No STUN/TURN servers are configured: the phone and Mac are on the same Tailscale
//  tunnel, so host candidates over the tunnel resolve directly. (aiortc on the Mac
//  likewise opens a direct peer connection.)
//
//  Requires the WebRTC binary framework. Add via Swift Package Manager:
//      https://github.com/stasel/WebRTC  (product name: WebRTC)
//  See README "Adding the WebRTC framework". The import below is `import WebRTC`.
//

import Foundation
import WebRTC
import os.log

/// High-level connection state surfaced to the UI and CallKit.
enum WebRTCState: Equatable {
    case idle
    case connecting
    case connected
    case failed(String)
    case closed
}

protocol WebRTCClientDelegate: AnyObject {
    func webRTCClient(_ client: WebRTCClient, didChange state: WebRTCState)
}

final class WebRTCClient: NSObject {

    // One process-wide factory. RTCInitializeSSL() must be called once before use and
    // RTCCleanupSSL() at teardown; we do that in AppDelegate's lifecycle.
    static let factory: RTCPeerConnectionFactory = {
        let encoder = RTCDefaultVideoEncoderFactory()
        let decoder = RTCDefaultVideoDecoderFactory()
        return RTCPeerConnectionFactory(encoderFactory: encoder, decoderFactory: decoder)
    }()

    weak var delegate: WebRTCClientDelegate?

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "webrtc")
    private var peerConnection: RTCPeerConnection?
    private var localAudioTrack: RTCAudioTrack?
    private var remoteAudioTrack: RTCAudioTrack?
    private let audioQueue = DispatchQueue(label: "ai.guruu.vera.audio")

    private(set) var state: WebRTCState = .idle {
        didSet { delegate?.webRTCClient(self, didChange: state) }
    }

    // MARK: - Connect

    /// Opens the peer connection, builds the local offer, POSTs it to the Mac, applies
    /// the answer. `offerURL` already carries the ?mode= query. `bearerToken` is the
    /// Mac's ANIMA_TOKEN (sent as Authorization: Bearer ...), or nil/empty to omit.
    func connect(offerURL: URL, bearerToken: String?) {
        state = .connecting

        let config = RTCConfiguration()
        // No ICE servers on purpose — direct over the tailnet tunnel. If you ever move
        // off Tailscale you'd add a STUN server here, e.g.:
        //   config.iceServers = [RTCIceServer(urlStrings: ["stun:stun.l.google.com:19302"])]
        config.iceServers = []
        config.sdpSemantics = .unifiedPlan
        // Gather all candidates, then send the offer once (the Mac has no trickle path).
        config.continualGatheringPolicy = .gatherOnce

        let constraints = RTCMediaConstraints(mandatoryConstraints: nil,
                                              optionalConstraints: nil)
        guard let pc = WebRTCClient.factory.peerConnection(with: config,
                                                           constraints: constraints,
                                                           delegate: self) else {
            state = .failed("Could not create RTCPeerConnection")
            return
        }
        self.peerConnection = pc

        addMicTrack(to: pc)

        let offerConstraints = RTCMediaConstraints(
            mandatoryConstraints: [
                kRTCMediaConstraintsOfferToReceiveAudio: kRTCMediaConstraintsValueTrue,
                kRTCMediaConstraintsOfferToReceiveVideo: kRTCMediaConstraintsValueFalse
            ],
            optionalConstraints: nil)

        pc.offer(for: offerConstraints) { [weak self] sdp, error in
            guard let self = self else { return }
            if let error = error {
                self.state = .failed("createOffer: \(error.localizedDescription)")
                return
            }
            guard let sdp = sdp else {
                self.state = .failed("createOffer returned no SDP")
                return
            }
            pc.setLocalDescription(sdp) { [weak self] error in
                guard let self = self else { return }
                if let error = error {
                    self.state = .failed("setLocalDescription: \(error.localizedDescription)")
                    return
                }
                // gatherOnce: wait until ICE gathering completes so the POSTed SDP carries
                // the host candidates. We poll the local description in the ICE state
                // callback; once complete we send whatever local description we have.
                self.maybeSendOffer(pc: pc, offerURL: offerURL, bearerToken: bearerToken)
            }
        }
    }

    private var offerSent = false

    /// Sends the offer once ICE gathering is complete (or immediately if already complete).
    private func maybeSendOffer(pc: RTCPeerConnection, offerURL: URL, bearerToken: String?) {
        // Capture the params; the actual POST fires from the ICE-gathering-complete callback
        // (or here, if gathering finished synchronously, which can happen with no ICE servers).
        self.pendingOffer = (pc, offerURL, bearerToken)
        if pc.iceGatheringState == .complete {
            sendPendingOffer()
        }
    }

    private var pendingOffer: (pc: RTCPeerConnection, url: URL, token: String?)?

    private func sendPendingOffer() {
        guard !offerSent, let pending = pendingOffer,
              let localSDP = pending.pc.localDescription else { return }
        offerSent = true

        var request = URLRequest(url: pending.url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = pending.token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 20

        // call_server expects exactly {"sdp": ..., "type": "offer"} and replies the same.
        let body: [String: String] = ["sdp": localSDP.sdp, "type": sdpTypeString(localSDP.type)]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        } catch {
            state = .failed("encode offer: \(error.localizedDescription)")
            return
        }

        log.info("POSTing offer to \(pending.url.absoluteString, privacy: .public)")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            if let error = error {
                self.state = .failed("offer POST failed: \(error.localizedDescription)")
                return
            }
            guard let http = response as? HTTPURLResponse else {
                self.state = .failed("offer POST: no HTTP response")
                return
            }
            guard (200..<300).contains(http.statusCode) else {
                self.state = .failed("offer POST: HTTP \(http.statusCode)")
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let answerSDP = json["sdp"] as? String,
                  let typeStr = json["type"] as? String else {
                self.state = .failed("offer POST: malformed answer JSON")
                return
            }
            let answer = RTCSessionDescription(type: self.sdpType(from: typeStr), sdp: answerSDP)
            pending.pc.setRemoteDescription(answer) { [weak self] error in
                guard let self = self else { return }
                if let error = error {
                    self.state = .failed("setRemoteDescription: \(error.localizedDescription)")
                    return
                }
                self.log.info("remote answer applied; waiting for media")
                // state -> .connected is driven by the RTCPeerConnectionDelegate connection
                // state callback below, mirroring call_server's connectionstatechange.
            }
        }.resume()
    }

    // MARK: - Mic / speaker

    private func addMicTrack(to pc: RTCPeerConnection) {
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let audioSource = WebRTCClient.factory.audioSource(with: constraints)
        let track = WebRTCClient.factory.audioTrack(with: audioSource, trackId: "vera-mic0")
        pc.add(track, streamIds: ["vera-stream0"])
        self.localAudioTrack = track
    }

    /// Mute/unmute the outgoing mic. The track stays in the connection; we just gate it.
    func setMuted(_ muted: Bool) {
        localAudioTrack?.isEnabled = !muted
    }

    /// Route her audio to the loudspeaker (true) or earpiece (false).
    func setSpeaker(_ loud: Bool) {
        audioQueue.async {
            let session = RTCAudioSession.sharedInstance()
            session.lockForConfiguration()
            defer { session.unlockForConfiguration() }
            do {
                if loud {
                    try session.overrideOutputAudioPort(.speaker)
                } else {
                    try session.overrideOutputAudioPort(.none)
                }
            } catch {
                self.log.error("speaker override failed: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Teardown

    func close() {
        peerConnection?.close()
        peerConnection = nil
        localAudioTrack = nil
        remoteAudioTrack = nil
        pendingOffer = nil
        offerSent = false
        state = .closed
    }

    // MARK: - SDP type helpers

    private func sdpTypeString(_ type: RTCSdpType) -> String {
        switch type {
        case .offer: return "offer"
        case .prAnswer: return "pranswer"
        case .answer: return "answer"
        case .rollback: return "rollback"
        @unknown default: return "offer"
        }
    }

    private func sdpType(from string: String) -> RTCSdpType {
        switch string.lowercased() {
        case "offer": return .offer
        case "pranswer": return .prAnswer
        case "answer": return .answer
        case "rollback": return .rollback
        default: return .answer
        }
    }
}

// MARK: - RTCPeerConnectionDelegate

extension WebRTCClient: RTCPeerConnectionDelegate {

    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceGatheringState) {
        log.debug("ICE gathering: \(newState.rawValue)")
        if newState == .complete {
            // gatherOnce finished — now the local SDP has all host candidates; send it.
            sendPendingOffer()
        }
    }

    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCPeerConnectionState) {
        log.info("connection state: \(newState.rawValue)")
        switch newState {
        case .connected:
            state = .connected
        case .failed:
            state = .failed("peer connection failed")
        case .closed:
            state = .closed
        case .disconnected:
            // Brief blips can self-heal over the tunnel; surface but don't hard-close.
            state = .failed("disconnected")
        default:
            break
        }
    }

    func peerConnection(_ pc: RTCPeerConnection, didAdd rtpReceiver: RTCRtpReceiver,
                        streams: [RTCMediaStream]) {
        if let track = rtpReceiver.track as? RTCAudioTrack {
            self.remoteAudioTrack = track
            track.isEnabled = true   // play her voice
            log.info("remote audio track added")
        }
    }

    // The remaining delegate methods are required by the protocol but unused for a
    // minimal audio call (no renegotiation, no data channel, no trickle ICE out).
    func peerConnectionShouldNegotiate(_ pc: RTCPeerConnection) {}
    func peerConnection(_ pc: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ pc: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ pc: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}
    func peerConnection(_ pc: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        // No trickle: candidates are folded into the offer via gatherOnce, so nothing to send.
    }
    func peerConnection(_ pc: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ pc: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}
