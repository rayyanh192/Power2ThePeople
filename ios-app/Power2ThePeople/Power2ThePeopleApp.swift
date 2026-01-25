import SwiftUI
import MWDATCore

@main
struct Power2ThePeopleApp: App {
    
    @StateObject private var wearablesManager = WearablesManager()
    
    init() {
        WearablesManager.configureWearablesOnce()
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(wearablesManager)
                .onOpenURL { url in
                    Task {
                        await wearablesManager.handleWearablesCallback(url: url)
                    }
                }
        }
    }
}
