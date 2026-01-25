//
//  AppState.swift
//  Power2ThePeople
//
//  Created by Rayyan Hussain on 1/25/26.
//

import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    // DGX endpoint (Tailscale IP or MagicDNS)
    @Published var dgxBaseURL: String = "http://promaxgb10-8528.tail3889eb.ts.net:8000"
    
    // Runtime state
    @Published var isRunning: Bool = false
    @Published var status: String = "Ready"
    @Published var lastResponse: String = ""
    
    // Session metadata
    let sessionID: String = UUID().uuidString
    @Published var seq: Int = 1
}
