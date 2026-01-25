import SwiftUI
import UIKit
import Combine
import MWDATCore
import MWDATCamera

@MainActor
final class WearablesManager: ObservableObject {
    
    private static var didConfigure: Bool = false
    
    // MARK: - Published UI State
    @Published var registrationStateText: String = "unknown"
    @Published var deviceCountText: String = "0 devices"
    @Published var cameraPermissionText: String = "unknown"
    @Published var isStreaming: Bool = false
    @Published var deviceCount: Int = 0
    @Published var lastErrorText: String? = nil
    
    @Published var latestFrameImage: UIImage? = nil
    @Published var lastPhotoCaptured: UIImage? = nil
    
    // MARK: - DAT Objects
    private lazy var wearables: any WearablesInterface = {
        WearablesManager.configureWearablesOnce()
        return Wearables.shared
    }()
    
    private var streamSession: StreamSession? = nil
    private var stateToken: Any? = nil
    private var frameToken: Any? = nil
    private var photoToken: Any? = nil
    
    private var registrationTask: Task<Void, Never>? = nil
    private var devicesTask: Task<Void, Never>? = nil
    
    init() {
        WearablesManager.configureWearablesOnce()
    }
    
    // MARK: - Configure
    static func configureWearablesOnce() {
        // Skip in Xcode Preview/Simulator
        if ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1" {
            return
        }
        
        #if targetEnvironment(simulator)
        return
        #else
        if didConfigure { return }
        didConfigure = true
        
        do {
            try Wearables.configure()
        } catch {
            print("Failed to configure Wearables SDK: \(error)")
        }
        #endif
    }
    
    // MARK: - Registration
    func startRegistration() {
        do {
            try wearables.startRegistration()
        } catch {
            print("startRegistration error: \(error)")
        }
    }
    
    func startUnregistration() {
        do {
            try wearables.startUnregistration()
        } catch {
            print("startUnregistration error: \(error)")
        }
    }
    
    func handleWearablesCallback(url: URL) async {
        do {
            _ = try await wearables.handleUrl(url)
        } catch {
            print("handleUrl error: \(error)")
        }
    }
    
    // MARK: - Device Discovery Streams
    func startObservingWearablesStreams() {
        // Listen to registration state changes
        registrationTask?.cancel()
        registrationTask = Task {
            for await state in wearables.registrationStateStream() {
                await MainActor.run {
                    self.registrationStateText = "\(state)"
                    self.lastErrorText = nil
                }
            }
        }
        
        // Listen to device discovery
        devicesTask?.cancel()
        devicesTask = Task {
            for await devices in wearables.devicesStream() {
                await MainActor.run {
                    self.deviceCount = devices.count
                    self.deviceCountText = "\(devices.count) devices"
                    self.lastErrorText = nil
                }
            }
        }
    }
    
    func stopObservingWearablesStreams() {
        registrationTask?.cancel()
        devicesTask?.cancel()
        registrationTask = nil
        devicesTask = nil
    }
    
    // MARK: - Camera Permissions
    func checkCameraPermission() {
        Task { [weak self] in
            guard let self else { return }
            guard self.deviceCount > 0 else {
                await MainActor.run {
                    self.cameraPermissionText = "blocked (0 devices)"
                    self.lastErrorText = "No glasses discovered. Register first."
                }
                return
            }
            do {
                let status = try await self.wearables.checkPermissionStatus(.camera)
                await MainActor.run {
                    self.cameraPermissionText = "\(status)"
                }
            } catch {
                await MainActor.run {
                    self.cameraPermissionText = "error"
                    self.lastErrorText = "checkPermissionStatus failed: \(error)"
                }
            }
        }
    }
    
    func requestCameraPermission() {
        Task { [weak self] in
            guard let self else { return }
            guard self.deviceCount > 0 else {
                await MainActor.run {
                    self.cameraPermissionText = "blocked (0 devices)"
                    self.lastErrorText = "Cannot request permission until Devices = 1+"
                }
                return
            }
            do {
                let status = try await self.wearables.requestPermission(.camera)
                await MainActor.run {
                    self.cameraPermissionText = "\(status)"
                }
            } catch {
                await MainActor.run {
                    self.cameraPermissionText = "error"
                    self.lastErrorText = "requestPermission failed: \(error)"
                }
            }
        }
    }
    
    // MARK: - Video Streaming
    func startStreaming() async {
        await stopStreaming()
        
        guard deviceCount > 0 else {
            await MainActor.run {
                self.isStreaming = false
                self.lastErrorText = "Cannot stream: no glasses discovered (Devices = 0)"
            }
            return
        }
        
        let deviceSelector = AutoDeviceSelector(wearables: wearables)
        let config = StreamSessionConfig(
            videoCodec: VideoCodec.raw,
            resolution: StreamingResolution.low,
            frameRate: 24
        )
        
        let session = StreamSession(streamSessionConfig: config, deviceSelector: deviceSelector)
        self.streamSession = session
        
        // Listen to session state
        stateToken = session.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                self?.isStreaming = (state == .streaming)
            }
        }
        
        // Listen to video frames
        frameToken = session.videoFramePublisher.listen { [weak self] frame in
            guard let image = frame.makeUIImage() else { return }
            Task { @MainActor in
                self?.latestFrameImage = image
            }
        }
        
        // Listen to photo captures
        photoToken = session.photoDataPublisher.listen { [weak self] photoData in
            if let img = UIImage(data: photoData.data) {
                Task { @MainActor in
                    self?.lastPhotoCaptured = img
                }
            }
        }
        
        await session.start()
    }
    
    func stopStreaming() async {
        guard let session = streamSession else { return }
        await session.stop()
        
        stateToken = nil
        frameToken = nil
        photoToken = nil
        
        streamSession = nil
        isStreaming = false
    }
    
    func capturePhoto() {
        guard let session = streamSession else { return }
        session.capturePhoto(format: .jpeg)
    }
}

struct ContentView: View {
    
    @StateObject private var mgr = WearablesManager()
    @StateObject private var stt = LiveSpeechTranscriber()
    @StateObject private var tts = TextToSpeechPlayer()
    
    var body: some View {
        NavigationView {
            VStack(spacing: 12) {
                
                // MARK: - Meta Glasses Status
                VStack(alignment: .leading, spacing: 6) {
                    Text("Registration: \(mgr.registrationStateText)")
                    Text("Devices: \(mgr.deviceCountText)")
                    Text("Camera Permission: \(mgr.cameraPermissionText)")
                    Text("Streaming: " + (mgr.isStreaming ? "YES" : "NO"))
                    
                    if let err = mgr.lastErrorText {
                        Text(err)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                
                Divider()
                
                // MARK: - Video Preview
                Group {
                    if let img = mgr.latestFrameImage {
                        Image(uiImage: img)
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: .infinity, maxHeight: 360)
                            .clipped()
                    } else {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(.gray.opacity(0.2))
                            .frame(height: 240)
                            .overlay(Text("No frame yet"))
                    }
                }
                
                Divider()
                
                // MARK: - MWDAT Controls
                HStack(spacing: 10) {
                    Button("Observe Streams") { mgr.startObservingWearablesStreams() }
                    Button("Register") { mgr.startRegistration() }
                    Button("Unregister") { mgr.startUnregistration() }
                }
                
                HStack(spacing: 10) {
                    Button("Check Cam Perm") { mgr.checkCameraPermission() }
                    Button("Request Cam Perm") { mgr.requestCameraPermission() }
                }
                
                HStack(spacing: 10) {
                    Button("Start Stream") { Task { await mgr.startStreaming() } }
                    Button("Stop Stream") { Task { await mgr.stopStreaming() } }
                    Button("Photo") { mgr.capturePhoto() }
                }
                
                if let photo = mgr.lastPhotoCaptured {
                    Divider()
                    Text("Last Photo")
                    Image(uiImage: photo)
                        .resizable()
                        .scaledToFit()
                        .frame(height: 140)
                }
                
                // MARK: - Live Transcription Section
                Divider()
                
                VStack(alignment: .leading, spacing: 8) {
                    Text("Live Transcription")
                        .font(.headline)
                    
                    Text("Status: \(stt.statusText)")
                        .font(.subheadline)
                    
                    if !stt.lastErrorText.isEmpty {
                        Text(stt.lastErrorText)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                    
                    // Mic Input Meter
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Mic Input")
                            .font(.subheadline)
                        
                        ProgressView(value: Double(stt.inputLevel))
                        
                        Text(String(format: "%.1f dB", stt.inputLevelDB))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    
                    // Transcript Display
                    RoundedRectangle(cornerRadius: 12)
                        .fill(.gray.opacity(0.12))
                        .frame(height: 140)
                        .overlay(
                            ScrollView {
                                Text(stt.transcript.isEmpty ? "(transcript will appear here…)" : stt.transcript)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                            }
                        )
                    
                    // Transcription Controls
                    HStack(spacing: 10) {
                        Button(stt.isRunning ? "Listening…" : "Start Mic STT") {
                            Task { await stt.start() }
                        }
                        .disabled(stt.isRunning)
                        
                        Button("Stop") {
                            stt.stop()
                        }
                        .disabled(!stt.isRunning)
                        
                        Button("Clear") {
                            stt.transcript = ""
                            stt.lastErrorText = ""
                            stt.statusText = "idle"
                        }
                    }
                    
                    Divider()
                    
                    // MARK: - Playback Controls
                    Text("Playback (Meta glasses speakers)")
                        .font(.headline)
                    
                    Text("Output route: \(tts.currentOutputRoute)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    if !tts.lastSpokenError.isEmpty {
                        Text(tts.lastSpokenError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                    
                    HStack(spacing: 10) {
                        Button(stt.isPlaybackPaused ? "Play" : "Pause") {
                            stt.playPausePlayback()
                        }
                        
                        Button("Restart") {
                            stt.restartPlayback()
                        }
                        
                        Button("Stop Playback") {
                            stt.stopPlayback()
                        }
                    }
                }
                
                Spacer()
            }
            .padding()
            .navigationTitle("MWDAT Stream")
        }
        .onOpenURL { url in
            Task { await mgr.handleWearablesCallback(url: url) }
        }
        .onAppear {
            Task { await stt.requestSpeechAuthorization() }
        }
    }
}
