//
//  CallController.swift
//  VeraCall
//
//  The bridge between iOS CallKit and Vera's WebRTC audio. It owns:
//    - the CXProvider (the native incoming-call UI + system call state)
//    - the CXCallController (so the app can request actions, e.g. end the call)
//    - the WebRTCClient (the actual audio peer to the Mac)
//
//  Flow for an *incoming* call (the normal case — the Mac rings the phone):
//    VoIP push arrives -> AppDelegate -> reportIncomingCall(...) here ->
//    CXProvider shows the full-screen swipe-to-answer screen -> user swipes ->
//    provider(_:perform: CXAnswerCallAction) -> we start the WebRTC connection.
//
//  Flow for an *outgoing* call (the in-app "Call Vera" button, for testing without push):
//    startOutgoingCall() -> CXStartCallAction -> on success we connect WebRTC.
//
//  CallKit requires the audio session to be configured but NOT activated by us before
//  answering; the provider calls provider(_:didActivate:) when it's our turn to start
//  audio. We start/route WebRTC audio there. See Apple's CallKit audio guidance.
//

import Foundation
import Combine
import CallKit
import AVFoundation
import WebRTC
import os.log

@MainActor
final class CallController: NSObject, ObservableObject {

    // What the in-call UI binds to.
    @Published private(set) var hasActiveCall = false
    @Published private(set) var connectionState: WebRTCState = .idle
    @Published var isMuted = false
    @Published var isSpeaker = true   // default to loudspeaker for a hands-free companion call

    /// Display name shown on the native call screen and in-app.
    let calleeName = "Vera"

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "call")
    // CXProvider is documented as safe to message from any thread; PushKit may invoke
    // reportIncomingCall(...) (which touches `provider`) from its own queue, so mark it
    // nonisolated to allow that without hopping actors — required to report the call
    // synchronously before the PushKit completion handler fires (iOS 13+ contract).
    private nonisolated let provider: CXProvider
    private let callController = CXCallController()
    private let webRTC = WebRTCClient()

    /// The settings are injected so the controller knows where the Mac is. Set by AppDelegate.
    weak var settings: VeraSettings?

    /// One call at a time; we track its UUID so CallKit actions map to it.
    private var currentCallID: UUID?

    override init() {
        self.provider = CXProvider(configuration: CallController.providerConfiguration())
        super.init()
        provider.setDelegate(self, queue: nil)
        webRTC.delegate = self
    }

    /// CXProviderConfiguration: how the system renders Vera's calls. Audio-only (video
    /// disabled), one call, generic handle type (we ring "Vera", not a phone number).
    static func providerConfiguration() -> CXProviderConfiguration {
        let config = CXProviderConfiguration()
        config.supportsVideo = false
        config.maximumCallGroups = 1
        config.maximumCallsPerCallGroup = 1
        config.supportedHandleTypes = [.generic]
        config.includesCallsInRecents = true
        // Drop a VeraCallIcon (40x40 template PNG) in the asset catalog to brand the
        // in-call screen; harmless if absent.
        if let icon = UIImage(named: "VeraCallIcon") {
            config.iconTemplateImageData = icon.pngData()
        }
        return config
    }

    // MARK: - Incoming (the Mac rings the phone via VoIP push)

    /// Report an incoming call to CallKit so iOS shows the native swipe-to-answer UI.
    /// Called from the PushKit handler. MUST be called synchronously inside
    /// pushRegistry(_:didReceiveIncomingPushWith:for:completion:) for a .voIP push,
    /// or iOS (13+) will terminate the app for not reporting a call.
    ///
    /// - Parameters:
    ///   - callID: a UUID for this call. If the push payload carries a "call_uuid",
    ///             pass it so the Mac and phone agree on the identifier.
    ///   - handle: what to show as the caller (defaults to "Vera").
    ///   - completion: invoked after CallKit has been told; forward this to PushKit.
    nonisolated func reportIncomingCall(callID: UUID,
                                        handle: String,
                                        completion: @escaping () -> Void) {
        let update = CXCallUpdate()
        update.remoteHandle = CXHandle(type: .generic, value: handle)
        update.localizedCallerName = handle
        update.hasVideo = false
        update.supportsHolding = false
        update.supportsGrouping = false
        update.supportsUngrouping = false
        update.supportsDTMF = false

        provider.reportNewIncomingCall(with: callID, update: update) { [weak self] error in
            if let error = error {
                // Reporting failed (e.g. Do Not Disturb policy rejected it). We still must
                // call completion so PushKit doesn't think we hung.
                self?.log.error("reportNewIncomingCall failed: \(error.localizedDescription)")
            } else {
                Task { @MainActor in self?.currentCallID = callID }
            }
            completion()
        }
    }

    // MARK: - Outgoing (in-app test button — no push required)

    /// Place a call to Vera from inside the app. Routes through CallKit so the audio
    /// session and call state are managed identically to an answered incoming call.
    func startOutgoingCall() {
        guard settings?.isConfigured == true else {
            connectionState = .failed("Set the Mac host in Settings first")
            return
        }
        let callID = UUID()
        let handle = CXHandle(type: .generic, value: calleeName)
        let startAction = CXStartCallAction(call: callID, handle: handle)
        startAction.isVideo = false
        let transaction = CXTransaction(action: startAction)
        callController.request(transaction) { [weak self] error in
            Task { @MainActor in
                guard let self = self else { return }
                if let error = error {
                    self.connectionState = .failed("start call: \(error.localizedDescription)")
                } else {
                    self.currentCallID = callID
                    self.provider.reportOutgoingCall(with: callID, startedConnectingAt: nil)
                }
            }
        }
    }

    // MARK: - End

    /// End the active call (the in-call hang-up button). Routes through CallKit so the
    /// system UI clears too. The actual WebRTC teardown happens in the End action handler.
    func endCall() {
        guard let callID = currentCallID else {
            // Nothing registered with CallKit; just make sure WebRTC is down.
            teardownWebRTC()
            return
        }
        let endAction = CXEndCallAction(call: callID)
        let transaction = CXTransaction(action: endAction)
        callController.request(transaction) { [weak self] error in
            if let error = error {
                self?.log.error("end call request: \(error.localizedDescription)")
                Task { @MainActor in self?.teardownWebRTC() }
            }
        }
    }

    func toggleMute() {
        isMuted.toggle()
        webRTC.setMuted(isMuted)
        // Reflect to CallKit so the system mute state stays in sync.
        if let callID = currentCallID {
            let action = CXSetMutedCallAction(call: callID, muted: isMuted)
            callController.request(CXTransaction(action: action)) { _ in }
        }
    }

    func toggleSpeaker() {
        isSpeaker.toggle()
        webRTC.setSpeaker(isSpeaker)
    }

    // MARK: - WebRTC plumbing

    /// Start the audio connection to the Mac. Called once CallKit hands us the activated
    /// audio session (provider(_:didActivate:)).
    private func startWebRTC() {
        guard let settings = settings, let url = settings.offerURL else {
            connectionState = .failed("Bad Mac URL — check Settings")
            return
        }
        let token = settings.authToken.isEmpty ? nil : settings.authToken
        webRTC.setSpeaker(isSpeaker)
        webRTC.setMuted(isMuted)
        webRTC.connect(offerURL: url, bearerToken: token)
    }

    private func teardownWebRTC() {
        webRTC.close()
        hasActiveCall = false
        currentCallID = nil
        isMuted = false
        connectionState = .idle
    }

    /// CallKit-managed audio session. We do NOT activate it ourselves; CallKit does and
    /// then calls provider(_:didActivate:). We only declare the category/mode here so the
    /// session is correctly configured for VoIP (voiceChat) before activation.
    private func configureAudioSession() {
        let session = RTCAudioSession.sharedInstance()
        session.lockForConfiguration()
        do {
            try session.setCategory(.playAndRecord,
                                    mode: .voiceChat,
                                    options: [.allowBluetoothHFP, .allowBluetoothA2DP])
        } catch {
            log.error("audio session config: \(error.localizedDescription)")
        }
        session.unlockForConfiguration()
    }
}

// MARK: - CXProviderDelegate

extension CallController: CXProviderDelegate {

    nonisolated func providerDidReset(_ provider: CXProvider) {
        // The provider was reset (e.g. the system tore down all calls). Drop everything.
        Task { @MainActor in self.teardownWebRTC() }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        // User swiped to answer. Configure (but don't activate) the audio session, mark the
        // call active, and let the system activate audio -> didActivate starts WebRTC.
        Task { @MainActor in
            self.configureAudioSession()
            self.hasActiveCall = true
            self.connectionState = .connecting
        }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        // Outgoing call accepted by the system. Same audio prep as answering.
        Task { @MainActor in
            self.configureAudioSession()
            self.hasActiveCall = true
            self.connectionState = .connecting
        }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        Task { @MainActor in self.teardownWebRTC() }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        Task { @MainActor in
            self.isMuted = action.isMuted
            self.webRTC.setMuted(action.isMuted)
        }
        action.fulfill()
    }

    // CallKit hands us the activated audio session here — THIS is where we start audio.
    nonisolated func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        let rtcSession = RTCAudioSession.sharedInstance()
        rtcSession.audioSessionDidActivate(audioSession)
        rtcSession.isAudioEnabled = true
        Task { @MainActor in self.startWebRTC() }
    }

    nonisolated func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        let rtcSession = RTCAudioSession.sharedInstance()
        rtcSession.audioSessionDidDeactivate(audioSession)
        rtcSession.isAudioEnabled = false
    }
}

// MARK: - WebRTCClientDelegate

extension CallController: WebRTCClientDelegate {
    nonisolated func webRTCClient(_ client: WebRTCClient, didChange state: WebRTCState) {
        Task { @MainActor in
            self.connectionState = state
            switch state {
            case .failed, .closed:
                // If the media dies, end the CallKit call too so the UI doesn't get stuck.
                if self.hasActiveCall { self.endCall() }
            default:
                break
            }
        }
    }
}
