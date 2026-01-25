//
//  CameraPreview.swift
//  Power2ThePeople
//
//  Created by Rayyan Hussain on 1/25/26.
//

import SwiftUI
import AVFoundation

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        view.layer.addSublayer(layer)
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        guard let layer = uiView.layer.sublayers?.first as? AVCaptureVideoPreviewLayer else { return }
        layer.session = session
        layer.frame = uiView.bounds
    }
}
