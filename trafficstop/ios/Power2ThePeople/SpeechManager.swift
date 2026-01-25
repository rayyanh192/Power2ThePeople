//
//  SpeechManager.swift
//  Power2ThePeople
//
//  Created by Rayyan Hussain on 1/25/26.
//

import Foundation
import Speech
import AVFoundation
import Combine

@MainActor
final class SpeechManager: ObservableObject {
    @Published var isRunning: Bool = false
    @Published var transcriptLive: String = ""
    @Published var status: String = "Idle"
    
    @Published var chunkBuffer: String = ""
    private var lastCommitted: String = ""

    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let recognizer = SFSpeechRecognizer()

    func requestPermissions() async {
        let speechAuth = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { authStatus in
                continuation.resume(returning: authStatus)
            }
        }

        let micGranted = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }

        if speechAuth != .authorized {
            status = "Speech permission not authorized"
        } else if !micGranted {
            status = "Microphone permission denied"
        } else {
            status = "Permissions OK"
        }
    }

    func start() {
        if isRunning { return }
        guard recognizer != nil else {
            status = "Speech recognizer unavailable"
            return
        }

        transcriptLive = ""
        status = "Starting…"

        do {
            let audioSession = AVAudioSession.sharedInstance()
            try audioSession.setCategory(.record, mode: .measurement, options: [.duckOthers])
            try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            status = "Audio session error: \(error.localizedDescription)"
            return
        }

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let recognitionRequest else {
            status = "Failed to create recognition request"
            return
        }
        recognitionRequest.shouldReportPartialResults = true

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)

        inputNode.removeTap(onBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
            self?.recognitionRequest?.append(buffer)
        }

        audioEngine.prepare()

        do {
            try audioEngine.start()
        } catch {
            status = "Audio engine start failed: \(error.localizedDescription)"
            return
        }

        recognitionTask = recognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }

            if let result = result {
                let text = result.bestTranscription.formattedString
                Task { @MainActor in
                    self.transcriptLive = text
                    self.chunkBuffer = text.replacingOccurrences(of: self.lastCommitted, with: "")
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    self.status = "Listening…"
                }
            }

            if let error = error {
                Task { @MainActor in
                    self.status = "STT error: \(error.localizedDescription)"
                    self.stop()
                }
            }
        }

        isRunning = true
        status = "Listening…"
    }

    func stop() {
        if !isRunning { return }

        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)

        recognitionRequest?.endAudio()
        recognitionTask?.cancel()

        recognitionRequest = nil
        recognitionTask = nil

        isRunning = false
        status = "Stopped"
    }
    
    func commitChunk() -> String {
        let chunk = chunkBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
        if chunk.isEmpty {
            return ""
        }
        // Mark everything so far as committed
        lastCommitted = transcriptLive
        chunkBuffer = ""
        return chunk
    }
}
