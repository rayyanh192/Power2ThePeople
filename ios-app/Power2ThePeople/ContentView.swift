//
//  ContentView.swift
//  Power2ThePeople
//
//  Created by Edrick Chang on 1/24/26.
//

import SwiftUI
import UIKit
import Combine
import CoreImage
import CoreMedia
import AVFoundation

// Meta Wearables Device Access Toolkit
import MWDATCore
import MWDATCamera

@MainActor
final class WearablesManager: ObservableObject {

    // MARK: - Published UI state
    @Published var registrationState: String = "unknown"
    @Published var deviceCount: String = "0"
    @Published var cameraPermission: String = "unknown"
    @Published var isStreaming: Bool = false
    @Published var errorMessage: String? = nil
    @Published var latestFrameImage: UIImage? = nil

    private var wearables: (any WearablesInterface)?
    private var streamSession: StreamSession?
    private var observationTasks: [Task<Void, Never>] = []
    private var isSimulator: Bool = false

    // Store stream listener tokens to keep subscriptions alive
    private var streamListeners: [Any] = []
    private var reconnectAttempts: Int = 0
    private let maxReconnectAttempts: Int = 5
    private var isReconnecting: Bool = false
    private var frameCount: Int = 0

    init() {
        #if targetEnvironment(simulator)
        isSimulator = true
        print("[MWDAT] Running in simulator - Wearables not available")
        #else
        // Configure Wearables SDK first, then access shared instance
        configureWearables()
        #endif

        // Start observing only if not in simulator
        if !isSimulator {
            startObserving()
        }
    }

    private func configureWearables() {
        do {
            try Wearables.configure()
            wearables = Wearables.shared
            print("[MWDAT] SDK configured successfully")
        } catch {
            print("[MWDAT] SDK configuration failed: \(error)")
            errorMessage = "SDK failed to initialize: \(error.localizedDescription)"
        }
    }

    var isSDKInitialized: Bool {
        return wearables != nil
    }
    
    private func startObserving() {
        guard let wearables = wearables else {
            print("[MWDAT] Cannot observe - wearables not initialized")
            return
        }

        // Stop any existing observations
        stopObserving()

        // Task 1: Observe registration state
        let registrationTask = Task {
            for await state in wearables.registrationStateStream() {
                await MainActor.run {
                    self.registrationState = "\(state)"
                    print("[MWDAT] Registration: \(state)")

                    // When registered (state 3), clear errors and check devices
                    if "\(state)".contains("3") || "\(state)".lowercased().contains("registered") {
                        self.errorMessage = nil  // Clear any stale registration errors
                        Task {
                            // Wait 3 seconds for system to stabilize
                            try? await Task.sleep(nanoseconds: 3_000_000_000)
                            await self.forceDeviceDiscovery()
                        }
                    }
                }
            }
        }
        observationTasks.append(registrationTask)

        // Task 2: Observe devices
        let devicesTask = Task {
            for await devices in wearables.devicesStream() {
                await MainActor.run {
                    self.deviceCount = "\(devices.count)"
                    print("[MWDAT] Devices: \(devices.count)")

                    if devices.count > 0 {
                        self.errorMessage = nil
                        // Auto-request camera permission when device appears
                        self.requestCameraPermissionIfNeeded()
                    } else {
                        self.errorMessage = "No glasses found. Make sure:\n1. Glasses are ON\n2. Paired with Meta AI app\n3. Bluetooth is ON"
                    }
                }
            }
        }
        observationTasks.append(devicesTask)
    }
    
    private func stopObserving() {
        for task in observationTasks {
            task.cancel()
        }
        observationTasks.removeAll()
    }
    
    private func forceDeviceDiscovery() async {
        guard let wearables = wearables else { return }

        print("[MWDAT] Forcing device discovery...")

        // Sometimes we need to manually trigger discovery
        // Some SDK versions have a refresh method
        let wearablesObject = wearables as AnyObject
        let selector = NSSelectorFromString("refreshDevices")
        if wearablesObject.responds(to: selector) {
            _ = wearablesObject.perform(selector)
            print("[MWDAT] Manual device refresh triggered")
        }

        // Also try to check devices through the stream
        try? await Task.sleep(nanoseconds: 2_000_000_000)
    }
    
    // MARK: - User Actions

    func register() {
        guard let wearables = wearables else {
            // Don't overwrite existing error if SDK failed to configure
            if errorMessage == nil || !errorMessage!.contains("SDK failed") {
                errorMessage = "SDK not initialized. Check console for errors."
            }
            return
        }

        print("[MWDAT] Starting registration...")
        errorMessage = nil

        do {
            try wearables.startRegistration()
        } catch {
            print("[MWDAT] Registration error: \(error)")
            errorMessage = "Registration failed: \(error.localizedDescription)"
        }
    }

    func unregister() {
        guard let wearables = wearables else { return }

        print("[MWDAT] Starting unregistration...")

        do {
            try wearables.startUnregistration()
        } catch {
            print("[MWDAT] Unregistration error: \(error)")
        }
    }

    func requestCameraPermissionIfNeeded() {
        guard let wearables = wearables else { return }

        Task {
            do {
                let status = try await wearables.checkPermissionStatus(.camera)
                await MainActor.run {
                    self.cameraPermission = "\(status)"
                }

                // If not granted, request it
                if !"\(status)".lowercased().contains("granted") {
                    let newStatus = try await wearables.requestPermission(.camera)
                    await MainActor.run {
                        self.cameraPermission = "\(newStatus)"
                    }
                }
            } catch {
                print("[MWDAT] Permission error: \(error)")
            }
        }
    }
    
    func startStream() async {
        guard let wearables = wearables else {
            errorMessage = "SDK not initialized"
            return
        }

        await stopStream()

        guard Int(deviceCount) ?? 0 > 0 else {
            errorMessage = "Cannot stream: No devices connected"
            return
        }

        // Check and request camera permission (but don't block if check fails)
        do {
            let status = try await wearables.checkPermissionStatus(.camera)
            print("[MWDAT] Camera permission status: \(status)")
            cameraPermission = "\(status)"

            if "\(status)".lowercased().contains("denied") {
                // Permission explicitly denied - this is blocking
                errorMessage = "Camera permission denied. Open Meta AI app → Settings → Connected Devices → Your app → Grant camera access"
                return
            }

            if !"\(status)".lowercased().contains("granted") {
                print("[MWDAT] Requesting camera permission...")
                let newStatus = try await wearables.requestPermission(.camera)
                print("[MWDAT] New camera permission status: \(newStatus)")
                cameraPermission = "\(newStatus)"

                // If still not granted after request, try streaming anyway
                // The SDK might prompt the user during stream start
                if "\(newStatus)".lowercased().contains("denied") {
                    errorMessage = "Camera permission denied. Please approve in Meta AI app."
                    return
                }
            }
        } catch {
            // Permission check failed - try streaming anyway
            // The SDK may handle permissions internally
            print("[MWDAT] Permission check error (proceeding anyway): \(error)")
            cameraPermission = "checking..."
        }

        print("[MWDAT] Starting stream...")
        errorMessage = nil
        frameCount = 0

        // Keep screen awake during streaming
        UIApplication.shared.isIdleTimerDisabled = true

        // Configure audio session to prevent Bluetooth disconnects (from SpecBridge)
        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothA2DP, .mixWithOthers])
            try audioSession.setActive(true)
            print("[MWDAT] Audio session configured for Bluetooth stability")
        } catch {
            print("[MWDAT] Audio session setup error: \(error)")
        }

        // Longer delay to let connection stabilize and "prime" the encoder
        if !isReconnecting {
            print("[MWDAT] Waiting for connection to stabilize (priming)...")
            try? await Task.sleep(nanoseconds: 2_000_000_000)
        }

        let deviceSelector = AutoDeviceSelector(wearables: wearables)
        // Use lower settings for more stable connection
        // Valid frameRate values: 2, 7, 15, 24, 30
        // Lower resolution reduces Bluetooth bandwidth pressure
        let config = StreamSessionConfig(
            videoCodec: VideoCodec.raw,
            resolution: StreamingResolution.low,
            frameRate: 15
        )

        let session = StreamSession(streamSessionConfig: config, deviceSelector: deviceSelector)
        self.streamSession = session

        // Clear previous listeners
        streamListeners.removeAll()

        // Listen for frames - MUST store the token to keep subscription alive
        let frameListener = session.videoFramePublisher.listen { [weak self] frame in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                self.frameCount += 1

                // Log every frame initially, then every 30th frame
                if self.frameCount <= 5 || self.frameCount % 30 == 0 {
                    print("[MWDAT] 📹 Frame #\(self.frameCount) received!")
                }

                if let image = frame.makeUIImage() {
                    self.latestFrameImage = image
                } else {
                    print("[MWDAT] ⚠️ Frame #\(self.frameCount) - makeUIImage() returned nil")
                }
            }
        }
        streamListeners.append(frameListener)

        // Listen for state changes - MUST store the token
        let stateListener = session.statePublisher.listen { [weak self] state in
            Task { @MainActor [weak self] in
                print("[MWDAT] Stream state changed: \(state)")

                switch state {
                case .streaming:
                    self?.isStreaming = true
                    self?.reconnectAttempts = 0
                    self?.isReconnecting = false
                    self?.errorMessage = nil
                    print("[MWDAT] ✅ Streaming active!")

                case .waitingForDevice:
                    self?.isStreaming = false
                    self?.errorMessage = "Waiting for glasses... Keep them awake"

                case .stopped:
                    self?.isStreaming = false
                    print("[MWDAT] Stream stopped")

                case .stopping:
                    self?.isStreaming = false

                default:
                    self?.isStreaming = false
                    // Handle stream errors
                    if "\(state)".lowercased().contains("error") || "\(state)".lowercased().contains("failed") {
                        self?.errorMessage = "Stream issue: \(state)"
                    }
                }
            }
        }
        streamListeners.append(stateListener)

        // Listen for errors - MUST store the token
        let errorListener = session.errorPublisher.listen { [weak self] error in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                print("[MWDAT] Stream error: \(error)")

                // Don't reconnect if already reconnecting
                guard !self.isReconnecting else {
                    print("[MWDAT] Already reconnecting, skipping...")
                    return
                }

                if self.reconnectAttempts < self.maxReconnectAttempts {
                    self.isReconnecting = true
                    self.reconnectAttempts += 1
                    self.errorMessage = "Stream error - Reconnecting (\(self.reconnectAttempts)/\(self.maxReconnectAttempts))..."
                    print("[MWDAT] Attempting reconnect \(self.reconnectAttempts)/\(self.maxReconnectAttempts)...")

                    // Longer delay between reconnects to let glasses recover
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    await self.startStream()
                    self.isReconnecting = false
                } else {
                    self.errorMessage = "Stream failed after \(self.maxReconnectAttempts) attempts. Tap Start Stream to try again."
                    self.reconnectAttempts = 0
                    self.isReconnecting = false
                }
            }
        }
        streamListeners.append(errorListener)

        await session.start()
        print("[MWDAT] Stream start() called")
    }
    
    func stopStream() async {
        guard let session = streamSession else { return }
        await session.stop()
        streamSession = nil
        streamListeners.removeAll()  // Clear listener tokens
        isStreaming = false
        latestFrameImage = nil
        reconnectAttempts = 0  // Reset reconnect counter
        isReconnecting = false
        frameCount = 0

        // Re-enable idle timer when not streaming
        UIApplication.shared.isIdleTimerDisabled = false

        // Deactivate audio session
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            print("[MWDAT] Audio session deactivation error: \(error)")
        }
    }

    func resetReconnectAttempts() {
        reconnectAttempts = 0
        isReconnecting = false
    }
    
    func handleCallback(url: URL) async {
        guard let wearables = wearables else { return }

        print("[MWDAT] Handling callback: \(url)")
        do {
            _ = try await wearables.handleUrl(url)
        } catch {
            print("[MWDAT] Callback error: \(error)")
        }
    }
}

// MARK: - ContentView
struct ContentView: View {
    @EnvironmentObject private var manager: WearablesManager
    @StateObject private var speechTranscriber = LiveSpeechTranscriber()
    @State private var showHelp = false
    @State private var isStatusExpanded = false
    @State private var isSpeechExpanded = false
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(spacing: 20) {
                        // Collapsible Status Card
                        VStack(alignment: .leading, spacing: 0) {
                            Button(action: { withAnimation { isStatusExpanded.toggle() } }) {
                                HStack {
                                    Text("Connection Status")
                                        .font(.headline)
                                    Spacer()
                                    Image(systemName: isStatusExpanded ? "chevron.up" : "chevron.down")
                                        .foregroundColor(.secondary)
                                }
                                .padding()
                                .background(Color(.systemGray6))
                                .contentShape(Rectangle())
                            }
                            .foregroundColor(.primary)
                            
                            if isStatusExpanded {
                                VStack(alignment: .leading, spacing: 10) {
                                    StatusRow(title: "📱 Registration", value: manager.registrationState)
                                    StatusRow(title: "👓 Devices Found", value: manager.deviceCount)
                                    StatusRow(title: "📷 Camera Access", value: manager.cameraPermission)
                                    StatusRow(title: "🎥 Streaming", value: manager.isStreaming ? "Active" : "Inactive")
                                    
                                    if let error = manager.errorMessage {
                                        Text(error)
                                            .foregroundColor(.red)
                                            .font(.caption)
                                            .padding(8)
                                            .background(Color.red.opacity(0.1))
                                            .cornerRadius(8)
                                    }
                                    
                                    Divider()
                                    
                                    // Help Button in dropdown
                                    Button(action: { showHelp = true }) {
                                        HStack {
                                            Image(systemName: "questionmark.circle")
                                            Text("Need Help?")
                                            Spacer()
                                        }
                                        .foregroundColor(.primary)
                                    }
                                    .padding(.top, 4)
                                }
                                .padding()
                                .background(Color(.systemGray6))
                            }
                        }
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                        
                        // Camera Feed
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Camera Feed")
                                .font(.headline)

                            if let image = manager.latestFrameImage {
                                Image(uiImage: image)
                                    .resizable()
                                    .scaledToFit()
                                    .frame(height: 200)
                                    .cornerRadius(12)
                            } else {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color(.systemGray5))
                                        .frame(height: 200)

                                    VStack(spacing: 12) {
                                        if manager.isStreaming {
                                            ProgressView()
                                                .scaleEffect(1.5)
                                            Text("Waiting for frames...")
                                                .foregroundColor(.gray)
                                            Text("Keep glasses awake")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        } else {
                                            Image(systemName: "camera.viewfinder")
                                                .font(.largeTitle)
                                                .foregroundColor(.gray)
                                            Text("No feed available")
                                                .foregroundColor(.gray)
                                            Text("Tap Start Stream")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Control Buttons
                        VStack(spacing: 15) {
                            // Registration Buttons
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Step 1: Registration")
                                    .font(.subheadline)
                                    .bold()
                                
                                HStack(spacing: 10) {
                                    Button(action: { manager.register() }) {
                                        Label("Register with Meta", systemImage: "link")
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .disabled(manager.registrationState.contains("registered"))
                                    
                                    Button(action: { manager.unregister() }) {
                                        Label("Unregister", systemImage: "link.slash")
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.bordered)
                                }
                            }
                            
                            // Streaming Buttons
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Step 2: Streaming")
                                    .font(.subheadline)
                                    .bold()
                                
                                HStack(spacing: 10) {
                                    Button(action: {
                                        Task {
                                            manager.resetReconnectAttempts()
                                            await manager.startStream()
                                        }
                                    }) {
                                        Label("Start Stream", systemImage: "play.circle")
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .disabled(manager.isStreaming || manager.deviceCount == "0")
                                    
                                    Button(action: {
                                        Task { await manager.stopStream() }
                                    }) {
                                        Label("Stop Stream", systemImage: "stop.circle")
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.bordered)
                                    .disabled(!manager.isStreaming)
                                }
                            }
                        }
                    }
                    .padding()
                }
                
                Divider()
                
                // Speech-to-Text Section (Collapsible)
                VStack(spacing: 0) {
                    Button(action: { withAnimation { isSpeechExpanded.toggle() } }) {
                        HStack {
                            Text("Speech to Text")
                                .font(.headline)
                            Spacer()
                            Image(systemName: isSpeechExpanded ? "chevron.up" : "chevron.down")
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color(.systemGray6))
                        .contentShape(Rectangle())
                    }
                    .foregroundColor(.primary)
                    
                    if isSpeechExpanded {
                        VStack(spacing: 12) {
                            // Microphone Level Indicator
                            VStack(spacing: 6) {
                                HStack {
                                    Image(systemName: "waveform")
                                        .foregroundColor(.blue)
                                    Text("Microphone Level")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Spacer()
                                    Text("\(Int(speechTranscriber.inputLevelDB)) dB")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .monospacedDigit()
                                }
                                
                                // Audio Level Bar
                                GeometryReader { geometry in
                                    ZStack(alignment: .leading) {
                                        RoundedRectangle(cornerRadius: 4)
                                            .fill(Color(.systemGray5))
                                        
                                        RoundedRectangle(cornerRadius: 4)
                                            .fill(
                                                LinearGradient(
                                                    gradient: Gradient(colors: [.green, .yellow, .red]),
                                                    startPoint: .leading,
                                                    endPoint: .trailing
                                                )
                                            )
                                            .frame(width: geometry.size.width * CGFloat(speechTranscriber.inputLevel))
                                    }
                                    .frame(height: 8)
                                }
                                .frame(height: 8)
                            }
                            .padding(.horizontal)
                            .padding(.top, 12)
                            
                            // Transcript Display
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Transcript")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .padding(.horizontal)
                                
                                ScrollView {
                                    TextEditor(text: $speechTranscriber.transcript)
                                        .frame(minHeight: 100)
                                        .padding(8)
                                        .background(Color(.systemGray6))
                                        .cornerRadius(8)
                                        .disabled(true)
                                }
                                .frame(height: 120)
                                .background(Color(.systemGray5))
                                .cornerRadius(8)
                                .padding(.horizontal)
                            }
                            
                            // Recording Controls
                            VStack(spacing: 12) {
                                HStack(spacing: 12) {
                                    Button(action: {
                                        Task {
                                            await speechTranscriber.start()
                                        }
                                    }) {
                                        HStack {
                                            Image(systemName: "mic.circle.fill")
                                            Text("Start Recording")
                                        }
                                        .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .disabled(speechTranscriber.isRunning)
                                    
                                    Button(action: {
                                        speechTranscriber.stop()
                                    }) {
                                        HStack {
                                            Image(systemName: "stop.circle.fill")
                                            Text("Stop Recording")
                                        }
                                        .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(.bordered)
                                    .disabled(!speechTranscriber.isRunning)
                                }
                                
                                Button(action: {
                                    speechTranscriber.transcript = ""
                                    speechTranscriber.savedTranscript = ""
                                }) {
                                    HStack {
                                        Image(systemName: "trash.circle")
                                        Text("Clear")
                                    }
                                    .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                
                                // Status Text
                                HStack {
                                    if speechTranscriber.isRunning {
                                        ProgressView()
                                            .scaleEffect(0.8)
                                    }
                                    Text(speechTranscriber.statusText)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Spacer()
                                }
                                .padding(.horizontal, 8)
                            }
                            .padding(.horizontal)
                            .padding(.bottom, 12)
                        }
                        .background(Color(.systemGray6))
                    }
                }
                .background(Color(.systemGray6))
            }
            .navigationTitle("Power2ThePeople")
            .sheet(isPresented: $showHelp) {
                HelpView()
            }
        }
        .onOpenURL { url in
            Task {
                await manager.handleCallback(url: url)
            }
        }
    }
}

struct StatusRow: View {
    let title: String
    let value: String
    
    var body: some View {
        HStack {
            Text(title)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.medium)
                .foregroundColor(colorForValue(value))
        }
        .padding(.vertical, 4)
    }
    
    func colorForValue(_ value: String) -> Color {
        let lower = value.lowercased()
        if lower.contains("registered") || lower.contains("granted") || lower.contains("active") || Int(value) ?? 0 > 0 {
            return .green
        } else if lower.contains("error") || lower.contains("failed") {
            return .red
        } else {
            return .primary
        }
    }
}

struct HelpView: View {
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            List {
                Section("Common Issues & Fixes") {
                    HelpItem(
                        icon: "exclamationmark.triangle",
                        title: "Registration Drops Immediately",
                        description: "This is normal! Wait 30 seconds after registration. The SDK often resets once before stabilizing."
                    )
                    
                    HelpItem(
                        icon: "eyeglasses",
                        title: "Glasses Not Found",
                        description: "1. Open Meta AI app\n2. Check glasses are connected (green dot)\n3. Enable Developer Mode in Meta AI Settings"
                    )
                    
                    HelpItem(
                        icon: "arrow.clockwise",
                        title: "Reset Everything",
                        description: "1. Close all apps\n2. Restart iPhone\n3. Restart glasses\n4. Open Meta AI → Pair glasses\n5. Try again"
                    )
                    
                    HelpItem(
                        icon: "gear",
                        title: "Developer Mode Required",
                        description: "In Meta AI app: Settings → Developer → Enable Developer Mode → Add your app's Bundle ID"
                    )
                }
                
                Section("Registration States Guide") {
                    HelpItem(
                        icon: "0.circle",
                        title: "State 0: Unknown",
                        description: "Initial state or error occurred"
                    )
                    
                    HelpItem(
                        icon: "1.circle",
                        title: "State 1: Unregistered",
                        description: "App is not registered with Meta"
                    )
                    
                    HelpItem(
                        icon: "2.circle",
                        title: "State 2: Registering",
                        description: "Registration in progress - wait"
                    )
                    
                    HelpItem(
                        icon: "3.circle.fill",
                        title: "State 3: Registered ✅",
                        description: "SUCCESS! App can now discover glasses"
                    )
                }
            }
            .navigationTitle("Troubleshooting Guide")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

struct HelpItem: View {
    let icon: String
    let title: String
    let description: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(.blue)
                    .frame(width: 30)
                Text(title)
                    .fontWeight(.medium)
            }
            Text(description)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.leading, 35)
        }
        .padding(.vertical, 5)
    }
}

#Preview {
    ContentView()
        .environmentObject(WearablesManager())
}
