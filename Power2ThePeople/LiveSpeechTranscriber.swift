import Foundation
import Speech
import AVFoundation
import Combine

@MainActor
final class LiveSpeechTranscriber: ObservableObject {
    
    @Published var transcript: String = ""
    @Published var savedTranscript: String = ""
    @Published var isRunning: Bool = false
    @Published var statusText: String = "idle"
    @Published var lastErrorText: String = ""
    
    @Published var inputLevel: Float = 0.0
    @Published var inputLevelDB: Float = -160.0
    
    @Published var isPlayingBack: Bool = false
    @Published var isPlaybackPaused: Bool = false
    
    private let audioEngine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let speechSynth = AVSpeechSynthesizer()
    
    private var levelTimer: Timer?
    
    func requestSpeechAuthorization() async {
        await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { _ in
                continuation.resume()
            }
        }
    }
    
    func start() async {
        transcript = ""
        lastErrorText = ""
        statusText = "requesting permissions…"
        
        // Request permissions
        await requestSpeechAuthorization()
        await requestMicrophonePermission()
        
        let session = AVAudioSession.sharedInstance()
        do {
            // Use .videoChat mode for voice processing + Bluetooth HFP mic support
            try session.setCategory(
                .playAndRecord,
                mode: .videoChat,
                options: [.duckOthers, .defaultToSpeaker, .allowBluetoothHFP, .allowBluetoothA2DP]
            )
            try session.setActive(true, options: .notifyOthersOnDeactivation)
            
            // Prefer Bluetooth HFP mic (Meta glasses) if available
            if let btMic = session.availableInputs?.first(where: { $0.portType == .bluetoothHFP }) {
                try session.setPreferredInput(btMic)
            }
            
            // Max input gain if device supports it
            if session.isInputGainSettable {
                try session.setInputGain(1.0)
            }
            
        } catch {
            lastErrorText = "Audio session setup failed: \(error)"
            statusText = "error"
            return
        }
        
        request = SFSpeechAudioBufferRecognitionRequest()
        guard let request else { return }
        
        request.shouldReportPartialResults = true
        
        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            request.append(buffer)
            self?.updateInputLevel(buffer: buffer)
        }
        
        audioEngine.prepare()
        do {
            try audioEngine.start()
            isRunning = true
            statusText = "listening…"
            
            // Start level monitoring
            startLevelTimer()
            
        } catch {
            lastErrorText = "AudioEngine start failed: \(error)"
            statusText = "error"
            return
        }
        
        task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result = result {
                Task { @MainActor in
                    self.transcript = result.bestTranscription.formattedString
                }
            }
            if error != nil {
                self.stop()
            }
        }
    }
    
    func stop() {
        // Save transcript before stopping
        savedTranscript = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        request = nil
        task?.cancel()
        task = nil
        
        levelTimer?.invalidate()
        levelTimer = nil
        inputLevel = 0.0
        inputLevelDB = -160.0
        
        isRunning = false
        statusText = "stopped"
    }
    
    private func requestMicrophonePermission() async {
        if #available(iOS 17.0, *) {
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                AVAudioApplication.requestRecordPermission { _ in
                    continuation.resume()
                }
            }
        } else {
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                AVAudioSession.sharedInstance().requestRecordPermission { _ in
                    continuation.resume()
                }
            }
        }
    }
    
    private func updateInputLevel(buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData else { return }
        let channelDataValue = channelData.pointee
        let channelDataArray = stride(from: 0, to: Int(buffer.frameLength), by: buffer.stride).map { channelDataValue[$0] }
        
        let rms = sqrt(channelDataArray.map { $0 * $0 }.reduce(0, +) / Float(buffer.frameLength))
        let avgPower = 20 * log10(rms)
        
        Task { @MainActor in
            self.inputLevelDB = avgPower
            // Normalize -60dB to 0dB range to 0.0 to 1.0
            let normalized = (avgPower + 60.0) / 60.0
            self.inputLevel = max(0.0, min(1.0, normalized))
        }
    }
    
    private func startLevelTimer() {
        levelTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            // Timer just ensures UI updates; actual level comes from updateInputLevel
        }
    }
    
    // MARK: - Playback Controls
    
    func playPausePlayback() {
        let textToSpeak = savedTranscript.isEmpty ? transcript : savedTranscript
        guard !textToSpeak.isEmpty else { return }
        
        if !speechSynth.isSpeaking {
            let utterance = AVSpeechUtterance(string: textToSpeak)
            utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
            speechSynth.speak(utterance)
            
            isPlayingBack = true
            isPlaybackPaused = false
            return
        }
        
        if isPlaybackPaused {
            speechSynth.continueSpeaking()
            isPlaybackPaused = false
        } else {
            speechSynth.pauseSpeaking(at: .word)
            isPlaybackPaused = true
        }
    }
    
    func restartPlayback() {
        let textToSpeak = savedTranscript.isEmpty ? transcript : savedTranscript
        guard !textToSpeak.isEmpty else { return }
        
        speechSynth.stopSpeaking(at: .immediate)
        
        let utterance = AVSpeechUtterance(string: textToSpeak)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        speechSynth.speak(utterance)
        
        isPlayingBack = true
        isPlaybackPaused = false
    }
    
    func stopPlayback() {
        speechSynth.stopSpeaking(at: .immediate)
        isPlayingBack = false
        isPlaybackPaused = false
    }
}
