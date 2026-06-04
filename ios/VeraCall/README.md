# VeraCall — the iPhone side of Vera's voice call

A native iOS app that lets **the Mac ring your iPhone** and connects you to Vera over a
direct WebRTC audio call. It is the phone-side peer for the Mac server in
`anima/call_server.py` + `anima/call_loop.py`.

- **Incoming call:** the Mac sends a **VoIP push** → iOS wakes VeraCall → it reports the
  call to **CallKit** → you get the native **full-screen swipe-to-answer** screen → you
  swipe → the app opens a **WebRTC** mic/audio call to the Mac and you talk to Vera.
- **Transport:** the phone reaches the Mac **directly over your Tailscale/WireGuard
  tunnel** (the Mac's tailnet hostname or `100.x` IP). **No STUN/TURN** — the tunnel is
  the network, exactly like the Mac's `aiortc` peer.
- **Outgoing test call:** a **Call Vera** button in the app dials the Mac immediately, so
  you can verify two-way audio **before** any push/Apple-account plumbing works.

> ⚠️ **You cannot run this on a real iPhone without an Apple Developer account.** CallKit,
> PushKit/VoIP, the microphone, and background audio all require a provisioned App ID and
> code signing. The Apple-account steps below are **yours to do** — they cannot be
> automated from here. (The app will *build* in the iOS Simulator without signing, but the
> Simulator cannot receive VoIP pushes, so real ringing needs a device + the steps below.)

---

## File tree

```
ios/VeraCall/
├─ README.md                         ← this file
├─ .gitignore                        ← ignores build output + signing secrets (*.p8 etc.)
├─ VeraCall.xcodeproj/               ← open THIS in Xcode
│  ├─ project.pbxproj
│  ├─ project.xcworkspace/…          ← + pinned SwiftPM dependency (stasel/WebRTC)
│  └─ xcshareddata/xcschemes/VeraCall.xcscheme
└─ VeraCall/
   ├─ Sources/
   │  ├─ VeraCallApp.swift           ← @main SwiftUI app; wires the AppDelegate
   │  ├─ AppDelegate.swift           ← PushKit VoIP registry; reports incoming calls
   │  ├─ CallController.swift        ← CXProvider/CXProviderDelegate + WebRTC orchestration
   │  ├─ WebRTCClient.swift          ← RTCPeerConnection; mirrors the /calltest handshake
   │  ├─ DeviceRegistration.swift    ← POSTs the VoIP token to the Mac's /device endpoint
   │  ├─ Settings.swift              ← Mac host/port/token/mode, persisted
   │  ├─ RootView.swift              ← home screen + Call Vera button
   │  ├─ InCallView.swift            ← in-call UI: Vera label, state, mute, speaker, hang up
   │  └─ SettingsView.swift          ← editable Mac host/port/token + shows the VoIP token
   └─ Resources/
      ├─ Info.plist                  ← UIBackgroundModes (voip, audio) + mic usage string
      ├─ VeraCall.entitlements       ← aps-environment (Push Notifications)
      └─ Assets.xcassets/            ← app icon slot + accent color

anima/voip_push.py                   ← the Mac-side push sender (APNs HTTP/2 + JWT/.p8)
```

`anima/voip_push.py` is the **only** Python file added; nothing else under `anima/` is
modified. In particular `anima/server.py` and `anima/call_server.py` are untouched.

---

## How the pieces talk

```
                        VoIP push (APNs HTTP/2, JWT-signed)
   anima/voip_push.py  ───────────────────────────────────────▶  iPhone (PushKit)
   (reads phone's VoIP token from .anima/<name>.device.json)         │
                                                                     ▼
                                                        CallKit swipe-to-answer
                                                                     │ (you swipe)
                                                                     ▼
   anima/call_server.py  ◀──── POST /webrtc_offer {sdp,type} ──── WebRTCClient.swift
        :8766 (ANIMA_CALL_PORT)  ───▶ {sdp,type} answer ─────────────▶ (audio flows)
   anima/call_loop.py  = Vera greets / VAD+STT / TTS reply

   DeviceRegistration.swift  ──── POST /device {voip_token,…} ────▶  anima/server.py
        (registers the phone)        :8765 (Bearer ANIMA_TOKEN)        /device endpoint
```

The WebRTC handshake in `WebRTCClient.swift` is a 1:1 Swift port of the JavaScript on the
Mac's `GET /calltest` page: create offer → `setLocalDescription` → POST
`{"sdp":…, "type":"offer"}` to `/webrtc_offer?mode=loop` → apply the `{"sdp":…,
"type":"answer"}` reply. `?mode=echo` switches the Mac to mic-loopback for an audio test.

---

## Part A — Build & run the audio call (no push yet)

You can get **talking-to-Vera working first** and leave the ringing (Apple account) for
Part B.

### A1. Add the WebRTC framework (Swift Package Manager)

The project **already references** `stasel/WebRTC` via SPM (a prebuilt `WebRTC.xcframework`
binary — the only practical way to get WebRTC on iOS without compiling Chromium). When you
open `VeraCall.xcodeproj`, Xcode resolves it automatically. If it doesn't:

1. **File ▸ Add Package Dependencies…**
2. URL: `https://github.com/stasel/WebRTC.git`
3. Dependency Rule: **Up to Next Major**, from **`137.0.0`** (the package is versioned
   `1xx.0.0`, mirroring Chromium milestones — the GitHub releases read like `M147`, which
   is SPM version `147.0.0`).
4. Add the **WebRTC** library product to the **VeraCall** target.

> **Alternative — GoogleWebRTC (legacy CocoaPods):** the old `pod 'GoogleWebRTC'` is
> **deprecated/unmaintained** and 32-bit-bitcode era; **prefer `stasel/WebRTC`.** If you
> must use GoogleWebRTC, you'd add a `Podfile`, run `pod install`, open the generated
> `.xcworkspace` instead of the `.xcodeproj`, and change `import WebRTC` accordingly. This
> project is set up for `stasel/WebRTC` and that is the supported path.

### A2. Open & configure

1. `open ios/VeraCall/VeraCall.xcodeproj` (or from Xcode: **File ▸ Open…**).
2. Wait for **"Resolving Package Dependencies"** to finish (downloads the WebRTC binary).
3. Build: **⌘B**. It should compile for the **iOS Simulator** with no signing.

### A3. Point the app at your Mac

Run the app, tap **Settings**, and set:

- **Host:** your Mac's **tailnet** name (e.g. `vera-mac.tailnet.ts.net`) or its `100.x.y.z`
  Tailscale IP. *(Not a LAN IP unless the phone is also on that LAN; the whole point is the
  tunnel.)*
- **Port:** `8766` (matches `ANIMA_CALL_PORT` in `call_server.py`).
- **ANIMA_TOKEN:** the same token the Mac runs with. Sent as `Authorization: Bearer …`.
  Leave blank **only** if the Mac has `ANIMA_TOKEN` unset (local testing). *(Note:
  `call_server.py`'s `_offer` does not yet enforce the token — see its phase-2 TODO — but
  `/device` on the main server does, so set it once here for both.)*
- **Mode:** **Talk to Vera** (default) or **Echo (mic test)**.

### A4. Start the Mac server and call

On the Mac:

```bash
ANIMA_CALL_PORT=8766 python3 -m anima.call_server
```

On the phone, tap **Call Vera**. Grant the **microphone** prompt the first time. Within a
second or two you should hear Vera greet you (loop mode) or your own echo (echo mode).

> The Simulator can do this outgoing test call (mic + WebRTC work). It **cannot** receive
> VoIP pushes — for real ringing you need a physical iPhone and Part B.

---

## Part B — Make the Mac *ring* the phone (this needs your Apple account)

These steps **must be done by you** in your Apple Developer account; they involve identity,
signing, and a private key that this repo will never contain.

### ✅ Ordered checklist — the user's Apple steps to get a ringing phone

1. **Enrol in the Apple Developer Program** (≈$99/yr) at
   <https://developer.apple.com/account>. A free account can build to your own device but
   **cannot** create the APNs Auth Key needed to send pushes — VoIP ringing requires the
   paid program.

2. **Create an App ID (explicit bundle ID).** Developer portal ▸ **Certificates,
   Identifiers & Profiles ▸ Identifiers ▸ +** ▸ **App IDs** ▸ **App**.
   - Bundle ID (explicit): **`ai.guruu.vera.VeraCall`**
     *(this is the project's default `PRODUCT_BUNDLE_IDENTIFIER`; if you choose a different
     one, change it in Xcode ▸ target ▸ Signing & Capabilities **and** set
     `APNS_BUNDLE_ID` to match in Part B step 8).*
   - **Capabilities:** check **Push Notifications**. *(There is no separate "VoIP"
     checkbox in the portal anymore — VoIP rides on Push Notifications; the "voip"
     **background mode** is set in the app's Info.plist, already done for you.)*

3. **Create an APNs Auth Key (.p8).** Portal ▸ **Keys ▸ +**.
   - Name it (e.g. "Vera APNs"), enable **Apple Push Notification service (APNs)**,
     **Continue ▸ Register**.
   - **Download the `AuthKey_XXXXXXXXXX.p8`** — you can only download it **once**. Store it
     safely **outside this repo** (the `.gitignore` blocks `*.p8`, but keep it out anyway).
   - Note the **Key ID** (`XXXXXXXXXX`, 10 chars) shown on the key's page.

4. **Note your Team ID.** Portal ▸ **Membership** (top-right account ▸ Membership) — the
   10-char **Team ID**.

5. **Sign the app in Xcode.** Open the project ▸ select the **VeraCall** target ▸ **Signing
   & Capabilities**:
   - **Team:** select your team (this sets `DEVELOPMENT_TEAM`, currently blank).
   - Ensure **Automatically manage signing** is on; Xcode creates/downloads the
     provisioning profile for `ai.guruu.vera.VeraCall`.
   - Confirm these **Capabilities** are present (the project already declares them, but
     verify Xcode shows them): **Push Notifications**, and **Background Modes** with
     **Voice over IP** and **Audio, AirPlay, and Picture in Picture** checked.
     - If a capability is missing, click **+ Capability** and add it; Xcode will reconcile
       it with `VeraCall.entitlements` / `Info.plist`.

6. **Run on a *real* iPhone** (not the Simulator). Select your connected device, **⌘R**.
   Trust the developer profile on the phone if prompted (Settings ▸ General ▸ VPN & Device
   Management). Grant the **microphone** permission.

7. **Register the phone with the Mac.** On first launch the app obtains its **VoIP push
   token** and tries to auto-POST it to the Mac's **`/device`** endpoint
   (`http://<mac-host>:8765/device`, `Authorization: Bearer <ANIMA_TOKEN>`). You can also
   do it by hand — open **Settings** in the app, copy the **VoIP push token**, and:

   ```bash
   curl -X POST "http://vera-mac.tailnet.ts.net:8765/device" \
     -H "Authorization: Bearer $ANIMA_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"voip_token":"<PASTE_TOKEN>","platform":"ios","bundle_id":"ai.guruu.vera.VeraCall"}'
   ```

   `anima/server.py`'s existing `/device` handler (`_store_device`) saves this to
   `.anima/<name>.device.json` as `voip_token`. **We do not modify `server.py`.** *(That
   endpoint is on the **main** server, default port **8765**, not the call server's 8766.)*

8. **Feed your keys to the push sender.** `anima/voip_push.py` reads everything from env —
   **no secrets are hardcoded**:

   ```bash
   export APNS_KEY_ID=XXXXXXXXXX                 # from step 3
   export APNS_TEAM_ID=YYYYYYYYYY                # from step 4
   export APNS_BUNDLE_ID=ai.guruu.vera.VeraCall  # from step 2 (must match the app)
   export APNS_KEY_PATH=/secure/path/AuthKey_XXXXXXXXXX.p8   # from step 3
   export APNS_ENV=sandbox        # dev builds run from Xcode use the sandbox APNs host;
                                  # set "production" for a TestFlight/App Store build
   pip install "httpx[http2]" PyJWT cryptography   # one-time deps for voip_push.py
   ```

9. **Ring the phone.**

   ```bash
   # ring whatever token the phone registered for "Vera":
   python3 -m anima.voip_push --ring
   # or ring an explicit token / custom caller label:
   python3 -m anima.voip_push --ring --token <hex> --handle "Vera"
   # dry run (prints host/topic/token without sending):
   python3 -m anima.voip_push
   ```

   Your iPhone should show the **native full-screen incoming call** for "Vera". **Swipe to
   answer** → the app connects WebRTC to `call_server.py` and you're talking to Vera.

> **Why swipe-to-answer (and not auto-answer)?** The native swipe-to-answer screen comes
> from CallKit's `reportNewIncomingCall(...)` and needs **no special entitlement** — it is
> the supported path and what this app uses. Apple also has a restricted entitlement,
> **`com.apple.developer.allow-auto-answer-calls`**, that would let a call connect with no
> swipe, but it is granted only for narrow approved use cases and is **rarely available**.
> This app deliberately does **not** depend on it; swipe-to-answer is the design.

---

## The VoIP push payload (what the Mac sends)

`voip_push.py` sends this JSON as the APNs body, with header `apns-push-type: voip` and
topic `<APNS_BUNDLE_ID>.voip`. `AppDelegate.swift` reads it in
`pushRegistry(_:didReceiveIncomingPushWith:for:completion:)`:

```json
{
  "aps": { "alert": "Vera is calling", "sound": "default" },
  "handle": "Vera",
  "call_uuid": "EAB3F1A2-1234-4C56-89AB-0123456789AB"
}
```

- `aps` — optional/cosmetic (VoIP pushes don't display an alert themselves; the call UI is
  CallKit). `handle` — the caller label shown on the call screen (defaults to "Vera").
  `call_uuid` — optional; if present the phone uses it as the CallKit call identifier so the
  Mac and phone agree on one id (handy if the Mac later wants to cancel a ring).

**Wiring Vera's brain to actually trigger a ring** (e.g. from a reminder escalation) is a
one-liner on the Mac, kept out of `server.py` per the task constraints:

```python
from anima import voip_push
voip_push.ring(name="Vera", handle="Vera")   # reads the registered token + your APNS_* env
```

---

## Notes, gotchas & troubleshooting

- **HTTP, not HTTPS, to the Mac is fine.** The WebRTC media is DTLS-SRTP encrypted and the
  signaling rides inside the Tailscale tunnel, so plain `http://…:8766/webrtc_offer` is
  acceptable here. (App Transport Security normally blocks cleartext HTTP; if your build's
  ATS rejects it, add an ATS exception for your tailnet host — but Tailscale's `…ts.net`
  over the tunnel typically just works.)
- **NordVPN / other full-tunnel VPNs break Tailscale.** If the call can't reach the Mac,
  make sure another VPN isn't capturing the route (a known issue for this setup).
- **VoIP push got the app killed / throttled?** iOS requires the app to call
  `reportNewIncomingCall` **synchronously** on every VoIP push before the completion
  handler — this app does. If you send VoIP pushes that *don't* result in a reported call,
  iOS will throttle them.
- **Sandbox vs production APNs:** a build run from Xcode (`aps-environment = development`)
  must be rung via the **sandbox** host (`APNS_ENV=sandbox`, the default). A TestFlight /
  App Store build (`aps-environment = production`) needs `APNS_ENV=production`. Mismatch →
  APNs returns `BadDeviceToken`.
- **`BadDeviceToken` / `DeviceTokenNotForTopic`:** token registered from the wrong build
  environment, or `APNS_BUNDLE_ID` doesn't match the app's bundle id. Re-register the token
  from the correct build and confirm the bundle id.
- **Deployment target:** iOS 16+ (set in the project; lower the `IPHONEOS_DEPLOYMENT_TARGET`
  if you must support older — the WebRTC binary itself supports iOS 12+, but the SwiftUI
  here uses iOS 16 APIs like `symbolEffect`).
- **App icon:** the asset catalog has an empty 1024×1024 slot; drop a PNG in
  `Resources/Assets.xcassets/AppIcon.appiconset` for a real icon (optional).
```
