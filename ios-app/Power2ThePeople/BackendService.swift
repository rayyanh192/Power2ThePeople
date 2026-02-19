import Foundation
import UIKit

/// Response from the /api/analyze endpoint
struct AnalyzeResponse: Codable {
    let advice: String
    let scene: String
}

/// Service for communicating with the Python backend via Tailscale
actor BackendService {

    /// The base URL for the backend (Tailscale IP + port)
    /// Update this with your Mac's Tailscale IP
    private let baseURL: String

    /// URLSession for making requests
    private let session: URLSession

    init(baseURL: String = "http://100.100.41.85:8000") { 
        self.baseURL = baseURL

        // Configure session with reasonable timeouts
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
    }

    /// Analyze a traffic stop scene
    /// - Parameters:
    ///   - transcript: What the officer said
    ///   - image: UIImage from the glasses camera
    /// - Returns: AnalyzeResponse with advice and scene description
    func analyze(transcript: String, image: UIImage) async throws -> AnalyzeResponse {
        guard let url = URL(string: "\(baseURL)/api/analyze") else {
            throw BackendError.invalidURL
        }

        // Convert image to JPEG data
        guard let imageData = image.jpegData(compressionQuality: 0.7) else {
            throw BackendError.imageConversionFailed
        }

        // Encode to base64
        let base64Image = imageData.base64EncodedString()

        // Create request body
        let requestBody: [String: Any] = [
            "transcript": transcript,
            "image": base64Image
        ]

        guard let jsonData = try? JSONSerialization.data(withJSONObject: requestBody) else {
            throw BackendError.encodingFailed
        }

        // Create request
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = jsonData

        print("[Backend] Sending request to \(url)...")
        print("[Backend] Transcript: \(transcript.prefix(50))...")
        print("[Backend] Image size: \(imageData.count / 1024) KB")

        // Make request
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }

        print("[Backend] Response status: \(httpResponse.statusCode)")

        guard httpResponse.statusCode == 200 else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw BackendError.serverError(statusCode: httpResponse.statusCode, message: errorMessage)
        }

        // Decode response
        let decoder = JSONDecoder()
        let analyzeResponse = try decoder.decode(AnalyzeResponse.self, from: data)

        print("[Backend] Received advice: \(analyzeResponse.advice)")

        return analyzeResponse
    }

    /// Check if the backend is reachable
    func healthCheck() async -> Bool {
        guard let url = URL(string: "\(baseURL)/health") else {
            return false
        }

        do {
            let (_, response) = try await session.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            return httpResponse.statusCode == 200
        } catch {
            print("[Backend] Health check failed: \(error)")
            return false
        }
    }
}

enum BackendError: LocalizedError {
    case invalidURL
    case imageConversionFailed
    case encodingFailed
    case invalidResponse
    case serverError(statusCode: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid backend URL"
        case .imageConversionFailed:
            return "Failed to convert image to JPEG"
        case .encodingFailed:
            return "Failed to encode request"
        case .invalidResponse:
            return "Invalid response from server"
        case .serverError(let statusCode, let message):
            return "Server error (\(statusCode)): \(message)"
        }
    }
}
