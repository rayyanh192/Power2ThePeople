import Foundation
import AVFoundation
import Combine

@MainActor
final class TextToSpeechPlayer: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    
    @Published var isSpeaking: Bool = false
    @Published var currentOutputRoute: String = "Unknown"
    @Published var lastSpokenError: String = ""
    
    private let synthesizer = AVSpeechSynthesizer()
    
    override init() {
        super.init()
        synthesizer.delegate = self
        refreshRouteLabel()
        
        NotificationCenter.default.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.refreshRouteLabel()
            }
        }
    }
    
    func speak(_ text: String) {
        guard !text.isEmpty else {
            lastSpokenError = "No text to speak"
            return
        }
        
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = 0.5
        
        synthesizer.speak(utterance)
        isSpeaking = true
        lastSpokenError = ""
    }
    
    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
        isSpeaking = false
    }
    
    private func refreshRouteLabel() {
        let session = AVAudioSession.sharedInstance()
        let route = session.currentRoute
        if let output = route.outputs.first {
            currentOutputRoute = output.portName
        } else {
            currentOutputRoute = "No output"
        }
    }
    
    // MARK: - AVSpeechSynthesizerDelegate
    
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.isSpeaking = false
            self.refreshRouteLabel()
        }
    }
    
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in
            self.isSpeaking = false
            self.refreshRouteLabel()
        }
    }
}
