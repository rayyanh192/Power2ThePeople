//
//  ContentView.swift
//  Power2ThePeople
//
//  Simplified version using iPhone camera and microphone only
//

import SwiftUI
import UIKit
import AVFoundation

// MARK: - ContentView
struct ContentView: View {
    @StateObject private var cameraManager = CameraManager()
    @StateObject private var speechTranscriber = LiveSpeechTranscriber()
    @StateObject private var ttsPlayer = TextToSpeechPlayer()

    // Backend integration
    @State private var isProcessingAdvice = false
    @State private var lastAdvice: String = ""
    @State private var backendError: String? = nil
    @State private var isRecording = false

    // TODO: Update this with your Mac's Tailscale IP
    private let backendService = BackendService(baseURL: "http://100.100.41.85:8000")

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Camera Preview
                ZStack {
                    Color.black

                    if cameraManager.isRunning {
                        CameraPreviewView(session: cameraManager.session)
                            .ignoresSafeArea()
                    } else {
                        VStack(spacing: 12) {
                            Image(systemName: "camera.fill")
                                .font(.system(size: 48))
                                .foregroundColor(.gray)
                            Text("Camera not active")
                                .foregroundColor(.gray)
                            if let error = cameraManager.errorMessage {
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.red)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                            }
                        }
                    }

                    // Recording indicator overlay
                    if isRecording {
                        VStack {
                            HStack {
                                Circle()
                                    .fill(Color.red)
                                    .frame(width: 12, height: 12)
                                Text("Recording")
                                    .font(.caption)
                                    .fontWeight(.bold)
                                    .foregroundColor(.white)
                            }
                            .padding(8)
                            .background(Color.black.opacity(0.6))
                            .cornerRadius(8)
                            .padding()

                            Spacer()
                        }
                    }

                    // Processing overlay
                    if isProcessingAdvice {
                        VStack {
                            Spacer()
                            HStack {
                                ProgressView()
                                    .tint(.white)
                                Text("Analyzing...")
                                    .foregroundColor(.white)
                                    .fontWeight(.medium)
                            }
                            .padding()
                            .background(Color.blue.opacity(0.8))
                            .cornerRadius(12)
                            .padding(.bottom, 20)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: UIScreen.main.bounds.height * 0.45)

                // Controls Section
                ScrollView {
                    VStack(spacing: 16) {
                        // Microphone Level
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
                                    .monospacedDigit()
                                    .foregroundColor(.secondary)
                            }

                            GeometryReader { geometry in
                                ZStack(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(Color(.systemGray5))
                                    RoundedRectangle(cornerRadius: 4)
                                        .fill(
                                            LinearGradient(
                                                colors: [.green, .yellow, .red],
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
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Transcript")
                                .font(.caption)
                                .foregroundColor(.secondary)

                            Text(speechTranscriber.transcript.isEmpty ? "Speak to see transcript..." : speechTranscriber.transcript)
                                .font(.body)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .frame(minHeight: 60)
                                .padding(10)
                                .background(Color(.systemGray6))
                                .cornerRadius(8)
                        }
                        .padding(.horizontal)

                        // Record Button
                        Button(action: toggleRecording) {
                            HStack {
                                Image(systemName: isRecording ? "stop.circle.fill" : "mic.circle.fill")
                                    .font(.title2)
                                Text(isRecording ? "Stop Recording" : "Start Recording")
                                    .fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(isRecording ? Color.red : Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(12)
                        }
                        .padding(.horizontal)

                        // Status
                        HStack {
                            if isRecording {
                                Text("Listening... pause for 1.5s to analyze")
                            } else {
                                Text("Tap to start recording")
                            }
                            Spacer()
                        }
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)

                        Divider()
                            .padding(.vertical, 8)

                        // Legal Advice Section
                        VStack(spacing: 12) {
                            HStack {
                                Text("Legal Advice")
                                    .font(.headline)
                                Spacer()
                                if ttsPlayer.isSpeaking {
                                    Image(systemName: "speaker.wave.2.fill")
                                        .foregroundColor(.green)
                                    Text("Speaking...")
                                        .font(.caption)
                                        .foregroundColor(.green)
                                }
                            }
                            .padding(.horizontal)

                            if let error = backendError {
                                Text(error)
                                    .font(.caption)
                                    .foregroundColor(.red)
                                    .padding(10)
                                    .frame(maxWidth: .infinity)
                                    .background(Color.red.opacity(0.1))
                                    .cornerRadius(8)
                                    .padding(.horizontal)
                            }

                            if !lastAdvice.isEmpty {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(lastAdvice)
                                        .font(.body)
                                        .padding(12)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .background(Color.blue.opacity(0.1))
                                        .cornerRadius(8)
                                }
                                .padding(.horizontal)

                                Button(action: {
                                    ttsPlayer.speak(lastAdvice)
                                }) {
                                    HStack {
                                        Image(systemName: "speaker.wave.2")
                                        Text("Replay Advice")
                                    }
                                    .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .padding(.horizontal)
                            } else {
                                Text("Advice will appear here after you speak")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .padding(.horizontal)
                            }
                        }
                        .padding(.bottom, 20)
                    }
                }
                .background(Color(.systemBackground))
            }
            .navigationTitle("Power2ThePeople")
            .navigationBarTitleDisplayMode(.inline)
        }
        .task {
            await cameraManager.setupCamera()
            cameraManager.start()
            setupPauseDetection()
        }
    }

    private func toggleRecording() {
        if isRecording {
            speechTranscriber.stop()
            isRecording = false
        } else {
            Task {
                await speechTranscriber.start()
                isRecording = true
            }
        }
    }

    /// Set up the pause detection callback
    private func setupPauseDetection() {
        speechTranscriber.onPauseDetected = { transcript in
            Task { @MainActor in
                await processWithBackend(transcript: transcript)
            }
        }
    }

    /// Send transcript and current frame to backend
    @MainActor
    private func processWithBackend(transcript: String) async {
        guard !isProcessingAdvice else {
            print("[App] Already processing, skipping...")
            return
        }

        guard let frameImage = cameraManager.captureCurrentFrame() else {
            print("[App] No camera frame available")
            backendError = "No camera frame available"
            return
        }

        isProcessingAdvice = true
        backendError = nil

        print("[App] Processing: \(transcript.prefix(50))...")

        do {
            let response = try await backendService.analyze(transcript: transcript, image: frameImage)
            lastAdvice = response.advice

            print("[App] Received advice: \(response.advice)")

            // Speak the advice
            ttsPlayer.speak(response.advice)

        } catch {
            print("[App] Backend error: \(error)")
            backendError = error.localizedDescription
        }

        isProcessingAdvice = false
    }
}

#Preview {
    ContentView()
}
