import SwiftUI
import UIKit

func uiImageFromJPEG(_ data: Data?) -> UIImage? {
    guard let data else { return nil }
    return UIImage(data: data)
}

struct ContentView: View {
    @StateObject private var state = AppState()
    @StateObject private var camera = CameraManager()
    @StateObject private var speech = SpeechManager()
    
    @StateObject private var vad = VADManager()
    @State private var readyTranscript: String = ""
    @State private var readyJPEGBytes: Int = 0
    @State private var lastTriggerTime: Date? = nil
    
    // NEW: DGX integration state
    @State private var pendingTranscript: String? = nil  // Waiting for snapshot
    @State private var dgxResponse: String = ""          // Advice from DGX
    @State private var isProcessing: Bool = false        // Loading indicator
    @State private var serverConnected: Bool? = nil      // Health check result
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 16) {
                    
                    // Camera preview
                    ZStack(alignment: .bottomLeading) {
                        CameraPreview(session: camera.session)
                            .frame(height: 320)
                            .clipped()
                            .cornerRadius(12)
                        
                        Text(camera.isRunning ? "Camera: ON" : "Camera: OFF")
                            .font(.footnote)
                            .padding(8)
                            .background(.ultraThinMaterial)
                            .cornerRadius(10)
                            .padding(12)
                    }
                    
                    // NEW: DGX Response box (prominent placement)
                    GroupBox(label: Label("Legal Advice", systemImage: "scale.3d")) {
                        VStack(alignment: .leading, spacing: 8) {
                            // Connection status
                            HStack {
                                Circle()
                                    .fill(serverConnected == true ? Color.green : (serverConnected == false ? Color.red : Color.gray))
                                    .frame(width: 8, height: 8)
                                Text(serverConnected == true ? "Server connected" : (serverConnected == false ? "Server offline" : "Checking..."))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Spacer()
                                Button("Retry") {
                                    checkServerHealth()
                                }
                                .font(.caption)
                            }
                            
                            Divider()
                            
                            if isProcessing {
                                HStack(spacing: 8) {
                                    ProgressView()
                                    Text("Analyzing scene...")
                                        .foregroundColor(.secondary)
                                }
                                .padding(.vertical, 8)
                            } else if dgxResponse.isEmpty {
                                Text("Waiting for first trigger...\n\nSpeak, then pause for 1.5s to get advice.")
                                    .foregroundColor(.secondary)
                                    .padding(.vertical, 8)
                            } else {
                                Text(dgxResponse)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(10)
                                    .background(Color.blue.opacity(0.1))
                                    .cornerRadius(10)
                            }
                        }
                    }
                    
                    GroupBox(label: Text("DGX Endpoint (Tailscale)")) {
                        TextField("http://100.x.y.z:8000", text: $state.dgxBaseURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .padding(.top, 4)
                    }
                    
                    HStack(spacing: 12) {
                        Button {
                            camera.start()
                            state.status = "Camera started"
                        } label: {
                            Text("Start Camera")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        
                        Button {
                            camera.stop()
                            state.status = "Camera stopped"
                        } label: {
                            Text("Stop Camera")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }
                    
                    Button {
                        camera.takeSnapshot()
                        state.status = "Snapshot requested…"
                    } label: {
                        Text("Snapshot (JPEG)")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .disabled(!camera.isRunning)
                    
                    GroupBox(label: Text("Status")) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(state.status)
                            if let t = camera.lastSnapshotTime {
                                Text("Last snapshot: \(t.formatted(date: .omitted, time: .standard))")
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                            } else {
                                Text("Last snapshot: none")
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                            }
                            Text("JPEG bytes: \(camera.lastSnapshotJPEG?.count ?? 0)")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                            if let img = uiImageFromJPEG(camera.lastSnapshotJPEG) {
                                Image(uiImage: img)
                                    .resizable()
                                    .scaledToFit()
                                    .frame(height: 180)
                                    .cornerRadius(10)
                            }
                        }
                    }
                    
                    GroupBox(label: Text("Speech-to-Text (on-device)")) {
                        VStack(alignment: .leading, spacing: 12) {
                            
                            Text("STT status: \(speech.status)")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                            
                            HStack(spacing: 12) {
                                Button {
                                    Task { await speech.requestPermissions() }
                                } label: {
                                    Text("Request Permissions")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                
                                Button {
                                    speech.start()
                                } label: {
                                    Text("Start Listening")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(speech.isRunning)
                                
                                Button {
                                    speech.stop()
                                } label: {
                                    Text("Stop")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .disabled(!speech.isRunning)
                            }
                            
                            Divider()
                            
                            Text("Live Transcript")
                                .font(.headline)
                            
                            Text(speech.transcriptLive.isEmpty ? "…" : speech.transcriptLive)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(10)
                                .background(Color.secondary.opacity(0.12))
                                .cornerRadius(10)
                        }
                    }
                    
                    GroupBox(label: Text("VAD (1.5s silence trigger)")) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("VAD status: \(vad.status) | level: \(String(format: "%.4f", vad.level))")
                                .font(.footnote)
                                .foregroundColor(.secondary)

                            HStack(spacing: 12) {
                                Button {
                                    Task { await speech.requestPermissions() }
                                } label: {
                                    Text("Ensure Permissions")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)

                                Button {
                                    vad.start()
                                    state.status = "VAD started"
                                } label: {
                                    Text("Start VAD")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(vad.isRunning)

                                Button {
                                    vad.stop()
                                    state.status = "VAD stopped"
                                } label: {
                                    Text("Stop VAD")
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(.bordered)
                                .disabled(!vad.isRunning)
                            }

                            Divider()

                            Text("Ready-to-send packet (debug)")
                                .font(.headline)

                            Text("Transcript chunk: \(readyTranscript.isEmpty ? "—" : readyTranscript)")
                                .font(.footnote)

                            Text("Last snapshot bytes: \(camera.lastSnapshotJPEG?.count ?? 0)")
                                .font(.footnote)

                            if let t = lastTriggerTime {
                                Text("Last trigger: \(t.formatted(date: .omitted, time: .standard))")
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    
                    Spacer()
                }
                .padding()
                .navigationTitle("Traffic Stop Assist")
            }
            .onAppear {
                // Check server health on launch
                checkServerHealth()
                
                // Set up VAD trigger
                vad.onSilenceTrigger = {
                    // 1) Freeze transcript chunk
                    let chunk = speech.commitChunk()
                    if chunk.isEmpty { return } // don't trigger on empty

                    readyTranscript = chunk
                    lastTriggerTime = Date()

                    // 2) Mark that we're waiting for a snapshot
                    pendingTranscript = chunk

                    // 3) Request snapshot
                    camera.takeSnapshot()

                    // 4) Update status
                    state.status = "Triggered: capturing snapshot..."
                }
            }
            // NEW: Watch for snapshot completion, then send to DGX
            .onChange(of: camera.lastSnapshotJPEG) { newData in
                guard let transcript = pendingTranscript,
                      let jpegData = newData,
                      let image = UIImage(data: jpegData) else { return }
                
                // Clear pending so we don't double-send
                pendingTranscript = nil
                isProcessing = true
                state.status = "Sending to DGX..."

                DGXService.shared.sendToBackend(transcript: transcript, image: image) { result in
                    DispatchQueue.main.async {
                        isProcessing = false
                        switch result {
                        case .success(let advice):
                            dgxResponse = advice
                            state.status = "✅ Got advice"
                        case .failure(let error):
                            dgxResponse = "⚠️ \(error.localizedDescription)"
                            state.status = "❌ \(error.localizedDescription)"
                        }
                    }
                }
            }
        }
    }
    
    // NEW: Health check function
    private func checkServerHealth() {
        serverConnected = nil
        DGXService.shared.checkHealth { isHealthy in
            DispatchQueue.main.async {
                serverConnected = isHealthy
            }
        }
    }
}
