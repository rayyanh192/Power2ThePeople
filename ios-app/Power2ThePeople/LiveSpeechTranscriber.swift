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
        transcript = ""  // Clear only when starting NEW recording session
        lastErrorText = ""
        statusText = "requesting permissions…"
        
        // Request permissions
        await requestSpeechAuthorization()
        await requestMicrophonePermission()
        
        let session = AVAudioSession.sharedInstance()
        do {
            // Use built-in mic only — no Bluetooth HFP so glasses mic is ignored
            try session.setCategory(
                .playAndRecord,
                mode: .measurement,
                options: [.duckOthers, .defaultToSpeaker, .allowBluetoothA2DP]
            )
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            // Explicitly route input to the iPhone's built-in microphone
            if let builtInMic = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
                try session.setPreferredInput(builtInMic)
            }

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
        
        input.removeTap(onBus: 0)
        
        // Get the format - it should not be nil for input node
        let format = input.outputFormat(forBus: 0) ?? AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)
        
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            request.append(buffer)
            self?.updateInputLevel(buffer: buffer)
        }
        
        audioEngine.prepare()
        do {
            try audioEngine.start()
            isRunning = true
            statusText = "listening…"
            startLevelTimer()
            
        } catch {
            lastErrorText = "AudioEngine start failed: \(error)"
            statusText = "error"
            return
        }
        
        task = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            guard let self = self else { return }
            if let result = result {
                Task { @MainActor in
                    self.transcript = result.bestTranscription.formattedString
                }
            }
            // Do NOT call stop() on error - let user explicitly stop
            // Do NOT clear transcript on task completion
            if let error = error {
                print("[Speech] Recognition error: \(error)")
                // Just log it, don't stop or clear
            }
        }
    }
    
    func stop() {
        // Save current transcript BEFORE stopping anything
        let currentText = transcript
        savedTranscript = currentText.trimmingCharacters(in: .whitespacesAndNewlines)
        
        print("[Speech] Stop called - current transcript: '\(currentText)'")
        
        // Stop audio capture
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        request = nil
        
        // Cancel the recognition task (this might trigger completion callback)
        task?.cancel()
        task = nil
        
        levelTimer?.invalidate()
        levelTimer = nil
        inputLevel = 0.0
        inputLevelDB = -160.0
        
        isRunning = false
        statusText = "stopped"
        
        // CRITICAL: Do NOT modify transcript here
        // Print confirmation
        print("[Speech] Stopped. Transcript still contains: '\(transcript)'")
    }
    
    private func requestMicrophonePermission() async {
        if #available(iOS 17.0, *) {
            await withCheckedContinuation { continuation in
                AVAudioApplication.requestRecordPermission { _ in
                    continuation.resume()
                }
            }
        } else {
            await withCheckedContinuation { continuation in
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
        let avgPower = rms > 0 ? 20 * log10(rms) : -160.0
        
        Task { @MainActor in
            self.inputLevelDB = avgPower
            let normalized = (avgPower + 60.0) / 60.0
            self.inputLevel = max(0.0, min(1.0, normalized))
        }
    }
    
    private func startLevelTimer() {
        // Timer is used to keep RunLoop active for audio level updates
        levelTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            // Level updates happen in updateInputLevel via audio tap callback
            _ = self
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
