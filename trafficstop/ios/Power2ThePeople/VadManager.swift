//
//  VadManager.swift
//  Power2ThePeople
//
//  Created by Rayyan Hussain on 1/25/26.
//

import Foundation
import AVFoundation
import Combine

@MainActor
final class VADManager: ObservableObject {
    @Published var isRunning: Bool = false
    @Published var level: Float = 0.0            // for UI/debug
    @Published var status: String = "Idle"

    // Tuning knobs
    var silenceThreshold: Float = 0.02           // tweak later
    var silenceDuration: TimeInterval = 1.5      // your requirement

    // Internal
    private let engine = AVAudioEngine()
    private var lastSpeechTime: Date = .distantPast

    // Callback when we detect end-of-utterance
    var onSilenceTrigger: (() -> Void)?

    func start() {
        if isRunning { return }

        status = "Starting…"
        lastSpeechTime = Date()

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: [.duckOthers])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            status = "Audio session error: \(error.localizedDescription)"
            return
        }

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)

        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            let rms = self.rmsLevel(buffer: buffer)
            DispatchQueue.main.async {
                self.level = rms

                let now = Date()
                if rms > self.silenceThreshold {
                    self.lastSpeechTime = now
                    self.status = "Speech"
                } else {
                    self.status = "Silence"
                    if now.timeIntervalSince(self.lastSpeechTime) >= self.silenceDuration {
                        // Fire once, then reset timer so it doesn't spam-trigger
                        self.lastSpeechTime = now
                        self.onSilenceTrigger?()
                    }
                }
            }
        }

        engine.prepare()

        do {
            try engine.start()
        } catch {
            status = "VAD engine start failed: \(error.localizedDescription)"
            return
        }

        isRunning = true
        status = "Running"
    }

    func stop() {
        if !isRunning { return }
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        isRunning = false
        status = "Stopped"
    }

    private func rmsLevel(buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.floatChannelData?[0] else { return 0 }
        let frameLength = Int(buffer.frameLength)
        if frameLength == 0 { return 0 }

        var sum: Float = 0
        for i in 0..<frameLength {
            let x = channelData[i]
            sum += x * x
        }
        return sqrt(sum / Float(frameLength))
    }
}
