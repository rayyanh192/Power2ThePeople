import Foundation
import AVFoundation
import UIKit
import SwiftUI

@MainActor
final class CameraManager: NSObject, ObservableObject {

    @Published var latestFrame: UIImage?
    @Published var isRunning: Bool = false
    @Published var errorMessage: String?

    private let captureSession = AVCaptureSession()
    private let videoOutput = AVCaptureVideoDataOutput()
    private let sessionQueue = DispatchQueue(label: "camera.session.queue")

    override init() {
        super.init()
    }

    /// Request camera permission
    func requestPermission() async -> Bool {
        let status = AVCaptureDevice.authorizationStatus(for: .video)

        switch status {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .video)
        case .denied, .restricted:
            errorMessage = "Camera access denied. Please enable in Settings."
            return false
        @unknown default:
            return false
        }
    }

    /// Set up the capture session
    func setupCamera() async {
        guard await requestPermission() else { return }

        sessionQueue.async { [weak self] in
            self?.configureCaptureSession()
        }
    }

    private func configureCaptureSession() {
        captureSession.beginConfiguration()
        captureSession.sessionPreset = .medium

        // Add video input (back camera preferred, fall back to front)
        guard let videoDevice = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
                ?? AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front) else {
            Task { @MainActor in
                self.errorMessage = "No camera available"
            }
            return
        }

        do {
            let videoInput = try AVCaptureDeviceInput(device: videoDevice)
            if captureSession.canAddInput(videoInput) {
                captureSession.addInput(videoInput)
            }
        } catch {
            Task { @MainActor in
                self.errorMessage = "Failed to access camera: \(error.localizedDescription)"
            }
            return
        }

        // Add video output
        videoOutput.setSampleBufferDelegate(self, queue: DispatchQueue(label: "camera.frame.queue"))
        videoOutput.alwaysDiscardsLateVideoFrames = true
        videoOutput.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]

        if captureSession.canAddOutput(videoOutput) {
            captureSession.addOutput(videoOutput)
        }

        captureSession.commitConfiguration()

        Task { @MainActor in
            self.errorMessage = nil
        }
    }

    /// Start the camera
    func start() {
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if !self.captureSession.isRunning {
                self.captureSession.startRunning()
                Task { @MainActor in
                    self.isRunning = true
                }
            }
        }
    }

    /// Stop the camera
    func stop() {
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if self.captureSession.isRunning {
                self.captureSession.stopRunning()
                Task { @MainActor in
                    self.isRunning = false
                }
            }
        }
    }

    /// Get the current frame as UIImage
    func captureCurrentFrame() -> UIImage? {
        return latestFrame
    }

    /// Get the AVCaptureSession for preview layer
    var session: AVCaptureSession {
        return captureSession
    }
}

// MARK: - AVCaptureVideoDataOutputSampleBufferDelegate
extension CameraManager: AVCaptureVideoDataOutputSampleBufferDelegate {
    nonisolated func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        let context = CIContext()

        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return }

        let uiImage = UIImage(cgImage: cgImage, scale: 1.0, orientation: .right)

        Task { @MainActor in
            self.latestFrame = uiImage
        }
    }
}

// MARK: - Camera Preview View
struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {
        // Layout is handled automatically by PreviewView
    }
}

/// Custom UIView that uses AVCaptureVideoPreviewLayer as its backing layer
class PreviewView: UIView {
    override class var layerClass: AnyClass {
        AVCaptureVideoPreviewLayer.self
    }

    var previewLayer: AVCaptureVideoPreviewLayer {
        layer as! AVCaptureVideoPreviewLayer
    }
}
