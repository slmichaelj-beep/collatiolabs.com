//
//  InCallView.swift
//  VeraCall
//
//  Minimal in-call surface shown while a call is live: the "Vera" label, the live
//  connection state, a mute toggle, a speaker toggle, and hang up. This is the in-app
//  screen; the native CallKit screen also appears for incoming calls / from the lock
//  screen — both drive the same CallController.
//
//  Design language (intake_ui_contract.md §0): calm stroke-style, single accent, generous
//  spacing, no heavy/filled glyphs except the destructive End Call circle. Muted gray for
//  secondary controls; accent blue (#2f7fff → .blue tint) only when active/accented.
//

import SwiftUI

// MARK: - Accent colors matching §0 palette

private extension Color {
    /// Active accent (#2f7fff)
    static let veraAccent = Color(red: 0.184, green: 0.498, blue: 1.0)
    /// Dim secondary (#8a8a8a)
    static let veraDim = Color(red: 0.541, green: 0.541, blue: 0.541)
    /// Background (#0a0a0a)
    static let veraBackground = Color(red: 0.039, green: 0.039, blue: 0.039)
    /// Surface (#141414)
    static let veraSurface = Color(red: 0.078, green: 0.078, blue: 0.078)
    /// Destructive red (#b91c1c)
    static let veraDestructive = Color(red: 0.725, green: 0.110, blue: 0.110)
}

// MARK: - InCallView

struct InCallView: View {
    @EnvironmentObject private var call: CallController

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            // Avatar — thin, breathable waveform ring instead of heavy filled circle
            VeraAvatar(active: call.connectionState == .connected,
                       muted: call.isMuted)
                .padding(.bottom, 28)

            Text(call.calleeName)
                .font(.system(size: 28, weight: .regular))
                .foregroundStyle(.white)

            Text(stateLabel)
                .font(.system(size: 14, weight: .regular))
                .foregroundStyle(stateLabelColor)
                .padding(.top, 6)
                .animation(.easeInOut(duration: 0.25), value: stateLabel)

            Spacer()

            // Secondary controls — mute + speaker, light weight
            HStack(spacing: 52) {
                CallButton(
                    label: call.isMuted ? "Unmuted" : "Mute",
                    systemImage: call.isMuted ? "mic.slash" : "mic",
                    isActive: false,
                    isHighlighted: call.isMuted
                ) {
                    call.toggleMute()
                }

                CallButton(
                    label: "Speaker",
                    systemImage: call.isSpeaker ? "speaker.wave.2" : "speaker",
                    isActive: call.isSpeaker,
                    isHighlighted: false
                ) {
                    call.toggleSpeaker()
                }
            }
            .padding(.bottom, 40)

            // End call — only control that uses a strong color (destructive per §0)
            Button {
                call.endCall()
            } label: {
                Image(systemName: "phone.down")
                    .font(.system(size: 24, weight: .medium))
                    .foregroundStyle(.white)
                    .frame(width: 68, height: 68)
                    .background(Circle().fill(Color.veraDestructive))
            }
            .padding(.bottom, 52)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.veraBackground.ignoresSafeArea())
    }

    // MARK: State label

    /// Human-readable call state. When connected, reflects whether the mic is live so the
    /// user knows their voice is going through (barge-in cooperation: mic is always live
    /// during Vera's playback; "Listening" simply confirms that state is normal).
    private var stateLabel: String {
        switch call.connectionState {
        case .idle:
            return "Starting…"
        case .connecting:
            return "Connecting…"
        case .connected:
            if call.isMuted {
                return "Muted"
            } else {
                return "Listening"
            }
        case .failed(let why):
            return "Connection lost · \(why)"
        case .closed:
            return "Call ended"
        }
    }

    private var stateLabelColor: Color {
        switch call.connectionState {
        case .connected:
            return call.isMuted ? Color.veraDim : Color.veraAccent.opacity(0.75)
        case .failed:
            return .red.opacity(0.8)
        default:
            return Color.veraDim
        }
    }
}

// MARK: - CallButton

/// A single secondary control: a thin-bordered circular button + small label beneath.
/// No filled backgrounds for inactive/default state — just a hairline stroke ring.
private struct CallButton: View {
    let label: String
    let systemImage: String
    /// When active the ring and icon take the accent color.
    let isActive: Bool
    /// When highlighted (e.g. muted) the icon uses a warning-adjacent dim orange tone,
    /// but stays low-weight — not the heavy ".orange" swatch used before.
    let isHighlighted: Bool
    let action: () -> Void

    private var iconColor: Color {
        if isHighlighted { return Color(red: 1.0, green: 0.60, blue: 0.20).opacity(0.85) }
        if isActive { return .veraAccent }
        return .veraDim
    }

    private var ringColor: Color {
        if isActive { return .veraAccent.opacity(0.35) }
        return Color.white.opacity(0.10)
    }

    var body: some View {
        VStack(spacing: 7) {
            Button(action: action) {
                Image(systemName: systemImage)
                    .font(.system(size: 22, weight: .light))
                    .foregroundStyle(iconColor)
                    .frame(width: 58, height: 58)
                    .background(
                        Circle()
                            .strokeBorder(ringColor, lineWidth: 1)
                    )
            }
            Text(label)
                .font(.system(size: 11, weight: .regular))
                .foregroundStyle(Color.veraDim)
        }
    }
}

// MARK: - VeraAvatar

/// Vera's call avatar. Uses a minimal "waveform" glyph inside a thin ring instead of the
/// heavy `waveform.circle.fill`. A gentle opacity pulse conveys presence without shouting.
/// On iOS 17+ the system symbolEffect(.variableColor) provides a calm breathing animation.
private struct VeraAvatar: View {
    let active: Bool
    /// When muted, the waveform dims — a quiet visual hint that the mic is off.
    let muted: Bool

    private var waveformOpacity: Double {
        if !active { return 0.35 }
        return muted ? 0.30 : 0.85
    }

    var body: some View {
        ZStack {
            // Thin outer ring — non-filled, matches §0 "stroke" sensibility
            Circle()
                .strokeBorder(Color.white.opacity(0.08), lineWidth: 1)
                .frame(width: 92, height: 92)

            // Inner waveform glyph (stroke-style SF Symbol)
            if #available(iOS 17.0, *) {
                Image(systemName: "waveform")
                    .font(.system(size: 34, weight: .ultraLight))
                    .foregroundStyle(Color.veraAccent)
                    .opacity(waveformOpacity)
                    .symbolEffect(.variableColor.iterative.dimInactiveLayers,
                                  isActive: active && !muted)
            } else {
                Image(systemName: "waveform")
                    .font(.system(size: 34, weight: .ultraLight))
                    .foregroundStyle(Color.veraAccent)
                    .opacity(waveformOpacity)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: muted)
        .animation(.easeInOut(duration: 0.3), value: active)
    }
}

// MARK: - Preview

#Preview {
    InCallView().environmentObject(CallController())
}
