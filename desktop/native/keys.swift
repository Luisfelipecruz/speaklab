// speaklab-keys: whether fn is held, for the main process. A listen-only event tap, which
// macOS allows only with Input Monitoring, and which sees every key; so what it prints is
// limited to four kinds of line, one JSON object each:
//
//   {"t":"access","granted":true}   Input Monitoring, at start and whenever it changes
//   {"t":"down","app":"Mail"}       fn went down, and the app in front at that moment
//   {"t":"up"}                      fn came up
//   {"t":"chord"}                   another key went down while fn was held
//
// It never prints, stores or sends which other key it was. --timestamps adds "ms", the
// wall clock in milliseconds, for the measurement harness; --no-request checks the
// permission without asking for it. It exits when stdin says "quit" or closes.

import AppKit
import CoreGraphics
import Foundation

let fnKeyCode: Int64 = 63
let arguments = Set(CommandLine.arguments.dropFirst())
let timestamps = arguments.contains("--timestamps")
let mayRequest = !arguments.contains("--no-request")

var fnDown = false
var tap: CFMachPort?
var granted = false

func emit(_ fields: [String: Any]) {
    var line = fields
    if timestamps { line["ms"] = (Date().timeIntervalSince1970 * 1000).rounded() }
    guard let data = try? JSONSerialization.data(withJSONObject: line, options: [.sortedKeys]) else { return }
    FileHandle.standardOutput.write(data + Data([0x0A]))
}

func release() {
    guard fnDown else { return }
    fnDown = false
    emit(["t": "up"])
}

let callback: CGEventTapCallBack = { _, type, event, _ in
    switch type {
    case .tapDisabledByTimeout, .tapDisabledByUserInput:
        // macOS switches off a tap that it judges slow; switched on again, it goes on.
        if let tap { CGEvent.tapEnable(tap: tap, enable: true) }
        if !CGEventSource.flagsState(.combinedSessionState).contains(.maskSecondaryFn) { release() }
    case .flagsChanged:
        let held = event.flags.contains(.maskSecondaryFn)
        if event.getIntegerValueField(.keyboardEventKeycode) == fnKeyCode {
            if held && !fnDown {
                fnDown = true
                emit(["t": "down", "app": NSWorkspace.shared.frontmostApplication?.localizedName ?? NSNull()])
            } else if !held {
                release()
            }
        } else if fnDown {
            emit(["t": "chord"])
        }
    case .keyDown:
        if fnDown { emit(["t": "chord"]) }
    default:
        break
    }
    return Unmanaged.passUnretained(event)
}

func startTap() -> Bool {
    let mask = (1 << CGEventType.flagsChanged.rawValue) | (1 << CGEventType.keyDown.rawValue)
    guard let created = CGEvent.tapCreate(
        tap: .cgSessionEventTap, place: .headInsertEventTap, options: .listenOnly,
        eventsOfInterest: CGEventMask(mask), callback: callback, userInfo: nil
    ) else { return false }
    tap = created
    CFRunLoopAddSource(CFRunLoopGetMain(), CFMachPortCreateRunLoopSource(nil, created, 0), .commonModes)
    CGEvent.tapEnable(tap: created, enable: true)
    return true
}

// The permission, now and as it changes: the person grants it in System Settings while
// this runs. A tap that cannot be made once it is granted exits, and the main process
// starts the helper again.
func checkAccess() {
    let now = CGPreflightListenEventAccess()
    if now != granted {
        granted = now
        emit(["t": "access", "granted": now])
        if now && tap == nil && !startTap() { exit(3) }
    }
}

FileHandle.standardInput.readabilityHandler = { handle in
    let data = handle.availableData
    if data.isEmpty || String(decoding: data, as: UTF8.self).contains("quit") { exit(0) }
}

granted = CGPreflightListenEventAccess()
if !granted && mayRequest { _ = CGRequestListenEventAccess() }
emit(["t": "access", "granted": granted])
if granted && !startTap() { exit(3) }

// fn's up can be lost: inside a password field macOS shows the tap nothing, and a tap it
// switched off misses what happened meanwhile. While fn is down, the flags say whether it
// still is.
Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
    if fnDown && !CGEventSource.flagsState(.combinedSessionState).contains(.maskSecondaryFn) { release() }
}
Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { _ in checkAccess() }

CFRunLoopRun()
