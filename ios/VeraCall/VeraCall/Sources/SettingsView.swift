//
//  SettingsView.swift
//  VeraCall
//
//  Configure where the Mac lives (tailnet host + call port), the shared ANIMA_TOKEN,
//  and the call mode (loop = talk to Vera, echo = mic loopback test). Also displays the
//  device's VoIP push token so you can register it with the Mac (it auto-registers to
//  /device too, but the token is shown here so you can copy it for a manual curl).
//

import SwiftUI
import UIKit   // UIPasteboard (copy VoIP token)

struct SettingsView: View {
    @EnvironmentObject private var settings: VeraSettings
    @Environment(\.dismiss) private var dismiss

    @State private var portText: String = ""
    @State private var voipToken: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("vera-mac.tailnet.ts.net", text: $settings.host)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    TextField("8766", text: $portText)
                        .keyboardType(.numberPad)
                        // iOS 16-compatible single-parameter onChange (the two-parameter
                        // (old, new) form is iOS 17+).
                        .onChange(of: portText) { newValue in
                            if let p = Int(newValue.filter(\.isNumber)), p > 0, p < 65536 {
                                settings.port = p
                            }
                        }
                } header: {
                    Text("Mac (over Tailscale)")
                } footer: {
                    Text("The Mac's tailnet hostname or 100.x tailnet IP, and the call "
                       + "server port (ANIMA_CALL_PORT, default 8766). No STUN/TURN — the "
                       + "phone reaches the Mac directly over the tunnel.")
                }

                Section {
                    SecureField("ANIMA_TOKEN (blank if unset)", text: $settings.authToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Shared secret")
                } footer: {
                    Text("Sent as Authorization: Bearer on the offer POST and on /device "
                       + "registration. Match the Mac's ANIMA_TOKEN. Leave blank only if "
                       + "the Mac runs with no token (local testing).")
                }

                Section {
                    Picker("Mode", selection: $settings.mode) {
                        Text("Talk to Vera").tag("loop")
                        Text("Echo (mic test)").tag("echo")
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text("Call mode")
                } footer: {
                    Text("\"Echo\" bounces your own mic back so you can confirm two-way "
                       + "audio before involving the conversation loop.")
                }

                Section {
                    if voipToken.isEmpty {
                        Text("Not yet received")
                            .foregroundStyle(.secondary)
                    } else {
                        Text(voipToken)
                            .font(.system(.footnote, design: .monospaced))
                            .textSelection(.enabled)
                        Button {
                            UIPasteboard.general.string = voipToken
                        } label: {
                            Label("Copy token", systemImage: "doc.on.doc")
                        }
                    }
                } header: {
                    Text("VoIP push token")
                } footer: {
                    Text("This device's PushKit token. It auto-registers to the Mac's "
                       + "/device endpoint, or copy it and POST it yourself (see README). "
                       + "This is the token voip_push.py sends the ring TO.")
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear { portText = String(settings.port) }
            .onReceive(NotificationCenter.default.publisher(for: .veraDidUpdateVoIPToken)) { note in
                if let t = note.userInfo?["token"] as? String { voipToken = t }
            }
        }
    }
}

#Preview {
    SettingsView().environmentObject(VeraSettings())
}
