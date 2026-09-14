//
//  RootView.swift
//  VeraCall
//
//  Top-level UI. When there's an active call we show the in-call screen; otherwise the
//  home screen with a "Call Vera" test button (so you can verify audio without waiting
//  for a push) and a gear into Settings.
//

import SwiftUI

struct RootView: View {
    @EnvironmentObject private var call: CallController
    @State private var showSettings = false

    var body: some View {
        ZStack {
            if call.hasActiveCall {
                InCallView()
            } else {
                HomeView(showSettings: $showSettings)
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .preferredColorScheme(.dark)
    }
}

struct HomeView: View {
    @EnvironmentObject private var call: CallController
    @EnvironmentObject private var settings: VeraSettings
    @Binding var showSettings: Bool

    var body: some View {
        VStack(spacing: 28) {
            Spacer()

            Image(systemName: "waveform.circle.fill")
                .resizable()
                .scaledToFit()
                .frame(width: 96, height: 96)
                .foregroundStyle(.tint)

            Text("Vera")
                .font(.largeTitle.weight(.semibold))

            Text(settings.isConfigured
                 ? "Ready · \(settings.host):\(settings.port)"
                 : "Set the Mac address in Settings")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Spacer()

            Button {
                call.startOutgoingCall()
            } label: {
                Label("Call Vera", systemImage: "phone.fill")
                    .font(.title3.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
            .disabled(!settings.isConfigured)
            .padding(.horizontal, 32)

            Button {
                showSettings = true
            } label: {
                Label("Settings", systemImage: "gearshape")
                    .font(.body)
            }
            .padding(.bottom, 24)
        }
        .padding()
    }
}

#Preview {
    HomeView(showSettings: .constant(false))
        .environmentObject(CallController())
        .environmentObject(VeraSettings())
}
