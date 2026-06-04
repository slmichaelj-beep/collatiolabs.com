//
//  InCallView.swift
//  VeraCall
//
//  Minimal in-call surface shown while a call is live: the "Vera" label, the live
//  connection state, a mute toggle, a speaker toggle, and hang up. This is the in-app
//  screen; the native CallKit screen also appears for incoming calls / from the lock
//  screen — both drive the same CallController.
//

import SwiftUI

struct InCallView: View {
    @EnvironmentObject private var call: CallController

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            PulsingWaveform(active: call.connectionState == .connected)

            Text(call.calleeName)
                .font(.system(size: 36, weight: .semibold))
                .padding(.top, 18)

            Text(stateLabel)
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(.top, 6)

            Spacer()

            HStack(spacing: 56) {
                CallButton(title: call.isMuted ? "Unmute" : "Mute",
                           systemImage: call.isMuted ? "mic.slash.fill" : "mic.fill",
                           tint: call.isMuted ? .orange : .gray) {
                    call.toggleMute()
                }
                CallButton(title: "Speaker",
                           systemImage: call.isSpeaker ? "speaker.wave.3.fill" : "speaker.fill",
                           tint: call.isSpeaker ? .blue : .gray) {
                    call.toggleSpeaker()
                }
            }
            .padding(.bottom, 44)

            Button {
                call.endCall()
            } label: {
                Image(systemName: "phone.down.fill")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 76, height: 76)
                    .background(Circle().fill(.red))
            }
            .padding(.bottom, 48)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.ignoresSafeArea())
    }

    private var stateLabel: String {
        switch call.connectionState {
        case .idle: return "Starting…"
        case .connecting: return "Connecting…"
        case .connected: return "Connected"
        case .failed(let why): return "Call failed · \(why)"
        case .closed: return "Ended"
        }
    }
}

private struct CallButton: View {
    let title: String
    let systemImage: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        VStack(spacing: 8) {
            Button(action: action) {
                Image(systemName: systemImage)
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 66, height: 66)
                    .background(Circle().fill(tint.opacity(0.85)))
            }
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

/// The call's pulsing avatar. The `.symbolEffect(.pulse)` animation is iOS 17+, so we gate
/// it on availability and fall back to a static icon on iOS 16.
private struct PulsingWaveform: View {
    let active: Bool

    var body: some View {
        let icon = Image(systemName: "waveform.circle.fill")
            .resizable()
            .scaledToFit()
            .frame(width: 110, height: 110)
            .foregroundStyle(.tint)
        if #available(iOS 17.0, *) {
            icon.symbolEffect(.pulse, isActive: active)
        } else {
            icon
        }
    }
}

#Preview {
    InCallView().environmentObject(CallController())
}
