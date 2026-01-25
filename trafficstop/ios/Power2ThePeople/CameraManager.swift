//
//  CameraManager.swift
//  Power2ThePeople
//
//  Created by Rayyan Hussain on 1/25/26.
//

import Foundation
import AVFoundation
import UIKit
import Combine

@MainActor
final class CameraManager: NSObject, ObservableObject {
    @Published var isRunning: Bool = false
    @Published var lastSnapshotJPEG: Data? = nil
    @Published var lastSnapshotTime: Date? = nil

    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()

    func start() {
        if isRunning { return }

        // 1) Request camera permission explicitly
        AVCaptureDevice.requestAccess(for: .video) { granted in
            DispatchQueue.main.async {
                if !granted {
                    print("Camera permission denied.")
                    return
                }

                // 2) Configure session only after permission granted
                self.session.beginConfiguration()
                self.session.sessionPreset = .high

                // Clear existing inputs/outputs to avoid "nothing happens" from bad state
                for input in self.session.inputs { self.session.removeInput(input) }
                for out in self.session.outputs { self.session.removeOutput(out) }

                guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                      let input = try? AVCaptureDeviceInput(device: device),
                      self.session.canAddInput(input) else {
                    print("Camera input setup failed.")
                    self.session.commitConfiguration()
                    return
                }
                self.session.addInput(input)

                if self.session.canAddOutput(self.output) {
                    self.session.addOutput(self.output)
                }

                self.session.commitConfiguration()
                self.session.startRunning()
                self.isRunning = true
            }
        }
    }

    func stop() {
        if !isRunning { return }
        session.stopRunning()
        isRunning = false
    }

    func takeSnapshot() {
        let settings = AVCapturePhotoSettings()
        settings.flashMode = .off
        output.capturePhoto(with: settings, delegate: self)
    }
}

extension CameraManager: AVCapturePhotoCaptureDelegate {
    func photoOutput(_ output: AVCapturePhotoOutput,
                     didFinishProcessingPhoto photo: AVCapturePhoto,
                     error: Error?) {
        if let error = error {
            print("Snapshot error: \(error)")
            return
        }
        guard let data = photo.fileDataRepresentation() else {
            print("Could not get JPEG data.")
            return
        }

        Task { @MainActor in
            self.lastSnapshotJPEG = data
            self.lastSnapshotTime = Date()
        }
    }
}
