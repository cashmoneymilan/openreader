import AppKit
import SwiftUI

@main
struct OpenReaderApp: App {
    @NSApplicationDelegateAdaptor(OpenReaderAppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .frame(minWidth: 920, minHeight: 640)
                .onAppear { appDelegate.engine = model.engine }
        }
        .defaultSize(width: 1060, height: 740)
        .windowToolbarStyle(.unified)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button("Choose PDF…") { model.requestFilePicker.toggle() }
                    .keyboardShortcut("o")
            }
        }
    }
}

@MainActor
final class OpenReaderAppDelegate: NSObject, NSApplicationDelegate {
    weak var engine: EngineSupervisor?

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    func applicationWillTerminate(_ notification: Notification) {
        engine?.stop()
    }
}
