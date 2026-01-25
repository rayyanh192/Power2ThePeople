import Foundation
import UIKit

// MARK: - DGX Service for Power2ThePeople

class DGXService {
    static let shared = DGXService()
    
    // MARK: - Configuration
    private let baseURL = "http://100.120.242.1:8000"
    private let authToken = "p2tp-hackathon-2024"
    private let timeoutSeconds: TimeInterval = 30
    
    // MARK: - Request State (prevents overlapping requests)
    private var isRequestInFlight = false
    private let lock = NSLock()
    
    private init() {}
    
    // MARK: - Main Ingest Function
    /// Call this when VAD triggers (1.5s silence detected)
    /// - Parameters:
    ///   - transcript: The speech-to-text transcript chunk
    ///   - image: The camera snapshot as UIImage
    ///   - completion: Returns the advice string or error
    func sendToBackend(
        transcript: String,
        image: UIImage,
        completion: @escaping (Result<String, DGXError>) -> Void
    ) {
        // Prevent overlapping requests
        lock.lock()
        if isRequestInFlight {
            lock.unlock()
            completion(.failure(.requestAlreadyInFlight))
            return
        }
        isRequestInFlight = true
        lock.unlock()
        
        // Convert image to JPEG data
        guard let imageData = image.jpegData(compressionQuality: 0.8) else {
            markRequestComplete()
            completion(.failure(.imageConversionFailed))
            return
        }
        
        // Build the request
        guard let url = URL(string: "\(baseURL)/ingest") else {
            markRequestComplete()
            completion(.failure(.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = timeoutSeconds
        
        // Auth header
        request.setValue(authToken, forHTTPHeaderField: "X-Auth-Token")
        
        // Multipart form data
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        
        // Add transcript field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"transcript\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(transcript)\r\n".data(using: .utf8)!)
        
        // Add image field
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"snapshot.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n".data(using: .utf8)!)
        
        // Close boundary
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        // Send request
        let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            defer { self?.markRequestComplete() }
            
            // Network error
            if let error = error {
                let nsError = error as NSError
                if nsError.code == NSURLErrorTimedOut {
                    completion(.failure(.timeout))
                } else if nsError.code == NSURLErrorNotConnectedToInternet ||
                          nsError.code == NSURLErrorCannotConnectToHost {
                    completion(.failure(.serverUnreachable))
                } else {
                    completion(.failure(.networkError(error.localizedDescription)))
                }
                return
            }
            
            // Check HTTP status
            guard let httpResponse = response as? HTTPURLResponse else {
                completion(.failure(.invalidResponse))
                return
            }
            
            guard (200...299).contains(httpResponse.statusCode) else {
                if httpResponse.statusCode == 401 {
                    completion(.failure(.unauthorized))
                } else {
                    completion(.failure(.serverError(statusCode: httpResponse.statusCode)))
                }
                return
            }
            
            // Parse response
            guard let data = data else {
                completion(.failure(.noData))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let advice = json["advice"] as? String {
                    completion(.success(advice))
                } else {
                    completion(.failure(.parseError))
                }
            } catch {
                completion(.failure(.parseError))
            }
        }
        
        task.resume()
    }
    
    // MARK: - Health Check
    func checkHealth(completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "\(baseURL)/health") else {
            completion(false)
            return
        }
        
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let httpResponse = response as? HTTPURLResponse,
               httpResponse.statusCode == 200 {
                completion(true)
            } else {
                completion(false)
            }
        }.resume()
    }
    
    // MARK: - Helpers
    private func markRequestComplete() {
        lock.lock()
        isRequestInFlight = false
        lock.unlock()
    }
}

// MARK: - Error Types

enum DGXError: Error, LocalizedError {
    case requestAlreadyInFlight
    case imageConversionFailed
    case invalidURL
    case timeout
    case serverUnreachable
    case networkError(String)
    case invalidResponse
    case unauthorized
    case serverError(statusCode: Int)
    case noData
    case parseError
    
    var errorDescription: String? {
        switch self {
        case .requestAlreadyInFlight:
            return "Still processing previous request..."
        case .imageConversionFailed:
            return "Failed to capture image"
        case .invalidURL:
            return "Invalid server URL"
        case .timeout:
            return "Server took too long to respond"
        case .serverUnreachable:
            return "Cannot reach server. Check Tailscale connection."
        case .networkError(let msg):
            return "Network error: \(msg)"
        case .invalidResponse:
            return "Invalid server response"
        case .unauthorized:
            return "Authentication failed"
        case .serverError(let code):
            return "Server error (code: \(code))"
        case .noData:
            return "No data received"
        case .parseError:
            return "Could not parse response"
        }
    }
}
