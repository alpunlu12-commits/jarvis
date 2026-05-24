import AppKit
import CoreGraphics
import Foundation

let args = CommandLine.arguments
let mode = args.count > 1 ? args[1] : "capture_active_window"
let outputPath = args.count > 2 ? args[2] : ""

func writeOutputFile(_ text: String) {
    guard !outputPath.isEmpty else { return }
    let url = URL(fileURLWithPath: outputPath)
    let directory = url.deletingLastPathComponent()
    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try? Data(text.utf8).write(to: url, options: .atomic)
}

func emit(_ payload: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: payload, options: []),
       let text = String(data: data, encoding: .utf8) {
        writeOutputFile(text)
        print(text)
    } else {
        let fallback = "{\"ok\":false,\"error\":\"json_encode_failed\"}"
        writeOutputFile(fallback)
        print(fallback)
    }
}

func cgIntValue(_ value: Any?) -> Int {
    if let number = value as? NSNumber {
        return number.intValue
    }
    if let number = value as? Int {
        return number
    }
    if let text = value as? String, let number = Int(text) {
        return number
    }
    return 0
}

func cgDoubleValue(_ value: Any?) -> Double {
    if let number = value as? NSNumber {
        return number.doubleValue
    }
    if let number = value as? Double {
        return number
    }
    if let number = value as? Int {
        return Double(number)
    }
    if let text = value as? String, let number = Double(text) {
        return number
    }
    return 0
}

func rectFromBounds(_ bounds: [String: Any]) -> CGRect {
    let x = cgDoubleValue(bounds["X"])
    let y = cgDoubleValue(bounds["Y"])
    let width = cgDoubleValue(bounds["Width"])
    let height = cgDoubleValue(bounds["Height"])
    return CGRect(x: x, y: y, width: width, height: height)
}

let currentPID = ProcessInfo.processInfo.processIdentifier

func visibleWindows() -> [[String: Any]] {
    guard let raw = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
        return []
    }

    return raw.filter { entry in
        let ownerPID = pid_t(cgIntValue(entry[kCGWindowOwnerPID as String]))
        if ownerPID == currentPID {
            return false
        }
        let layer = cgIntValue(entry[kCGWindowLayer as String])
        if layer != 0 {
            return false
        }
        let alpha = cgDoubleValue(entry[kCGWindowAlpha as String])
        if alpha <= 0.01 {
            return false
        }
        guard let bounds = entry[kCGWindowBounds as String] as? [String: Any] else {
            return false
        }
        let rect = rectFromBounds(bounds)
        return rect.width >= 80 && rect.height >= 60
    }
}

func windowCandidates(for pid: pid_t) -> [[String: Any]] {
    visibleWindows().filter { entry in
        let ownerPID = pid_t(cgIntValue(entry[kCGWindowOwnerPID as String]))
        return ownerPID == pid
    }
}

func bestWindow(for pid: pid_t) -> [String: Any]? {
    let candidates = windowCandidates(for: pid)
    if candidates.isEmpty {
        return nil
    }

    let sorted = candidates.sorted { left, right in
        let leftBounds = rectFromBounds((left[kCGWindowBounds as String] as? [String: Any]) ?? [:])
        let rightBounds = rectFromBounds((right[kCGWindowBounds as String] as? [String: Any]) ?? [:])
        let leftTitle = ((left[kCGWindowName as String] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let rightTitle = ((right[kCGWindowName as String] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let leftArea = leftBounds.width * leftBounds.height
        let rightArea = rightBounds.width * rightBounds.height

        if !leftTitle.isEmpty && rightTitle.isEmpty {
            return true
        }
        if leftTitle.isEmpty && !rightTitle.isEmpty {
            return false
        }
        return leftArea > rightArea
    }

    return sorted.first
}

func fallbackFrontmostWindow() -> [String: Any]? {
    let ignoredOwners = Set(["Window Server", "Dock", "Control Center", "Notification Center"])
    for entry in visibleWindows() {
        let ownerName = ((entry[kCGWindowOwnerName as String] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if ignoredOwners.contains(ownerName) {
            continue
        }
        return entry
    }
    return nil
}

func captureWindow(_ windowID: Int, to destination: URL) -> (Bool, String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    process.arguments = ["-x", "-o", "-l", String(windowID), destination.path]
    let outPipe = Pipe()
    let errPipe = Pipe()
    process.standardOutput = outPipe
    process.standardError = errPipe

    do {
        try process.run()
        process.waitUntilExit()
    } catch {
        return (false, "screencapture_failed: \(error.localizedDescription)")
    }

    let stderrData = errPipe.fileHandleForReading.readDataToEndOfFile()
    let stdoutData = outPipe.fileHandleForReading.readDataToEndOfFile()
    let detail = String(data: stderrData, encoding: .utf8) ?? String(data: stdoutData, encoding: .utf8) ?? ""
    if process.terminationStatus != 0 {
        return (false, detail.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    if !FileManager.default.fileExists(atPath: destination.path) {
        return (false, "screenshot_file_missing")
    }

    return (true, detail.trimmingCharacters(in: .whitespacesAndNewlines))
}

if mode != "capture_active_window" {
    emit([
        "ok": false,
        "error": "unsupported_mode",
        "detail": "Yalnizca capture_active_window destekleniyor.",
    ])
    exit(0)
}

let frontmostApp = NSWorkspace.shared.frontmostApplication
let candidateWindow =
    (frontmostApp != nil && frontmostApp!.processIdentifier != currentPID)
    ? bestWindow(for: frontmostApp!.processIdentifier)
    : nil

guard let window = candidateWindow ?? fallbackFrontmostWindow() else {
    emit([
        "ok": false,
        "error": "no_active_window",
        "detail": "Aktif pencere bulunamadi. Hedef pencereyi one alip tekrar dene.",
        "owner_name": frontmostApp?.localizedName ?? "",
    ])
    exit(0)
}

let windowID = cgIntValue(window[kCGWindowNumber as String])
let ownerName = (window[kCGWindowOwnerName as String] as? String) ?? (frontmostApp?.localizedName ?? "")
let windowTitle = (window[kCGWindowName as String] as? String) ?? ""
let bounds = (window[kCGWindowBounds as String] as? [String: Any]) ?? [:]
let rect = rectFromBounds(bounds)

let screenshotURL = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("jarvis-screen-\(UUID().uuidString).png")

let captureResult = captureWindow(windowID, to: screenshotURL)
if !captureResult.0 {
    let detail = captureResult.1.lowercased()
    let errorCode = detail.contains("permission") || detail.contains("not permitted") ? "permission_denied" : "capture_failed"
    emit([
        "ok": false,
        "error": errorCode,
        "detail": captureResult.1.isEmpty ? "Ekran goruntusu alinamadi." : captureResult.1,
        "owner_name": ownerName,
        "window_title": windowTitle,
    ])
    exit(0)
}

emit([
    "ok": true,
    "image_path": screenshotURL.path,
    "owner_name": ownerName,
    "window_title": windowTitle,
    "bounds": [
        "x": rect.origin.x,
        "y": rect.origin.y,
        "width": rect.width,
        "height": rect.height,
    ],
    "detail": captureResult.1,
])
