// Second brain menu-bar icon for macOS: dashboard status, quick job starts, failure notifications.
//
// UNTESTED: written on Windows, never compiled or run on a Mac. See README "Platform support".
//
// Build (install_jobs.py does it on macOS, before registering the job "second-brain.tray"):
//     swiftc -O -swift-version 5 -o ~/Library/Application\ Support/second-brain/SecondBrainTray SecondBrainTray.swift
// Needs only the Xcode Command Line Tools (already required for git). AppKit and Foundation only, no package.
// `SecondBrainTray --self-test` prints what the menu would show and the exact commands, then exits 0.
//
// Security notes:
// - Every launchd label and command comes from the fixed lists below. Nothing read from launchctl, the network or
//   the menu is used to build a label or a command; launchctl output is only parsed for numbers.
// - The health check talks only to 127.0.0.1:8765, with no proxy.
// - Notifications go through /usr/bin/osascript with the text passed as argv, never spliced into the script.
//   (UNUserNotificationCenter needs an app bundle with a bundle id; a bare swiftc binary has none and the call fails.)

import AppKit
import Foundation

let prefix = "second-brain"
let dashboardURL = URL(string: "http://127.0.0.1:8765/")!
// Cheapest GET of the dashboard (reads config.json only). URLSession sends Host 127.0.0.1:8765, which the server allows.
let healthURL = URL(string: "http://127.0.0.1:8765/api/moduli")!
let pollSeconds: TimeInterval = 30
// Fixed allowlist of the "Avvia job" menu: each group runs in order (feed first, radar once feed has ended).
let jobGroups: [[String]] = [["morning"], ["feed", "radar"], ["chiusura"], ["bozze"], ["pulizia"]]
// No exit-code check: the dashboard has its own up/down notification, the tray is this process.
let noFailureCheck: Set<String> = ["dashboard", "tray"]
let launchctlPath = "/bin/launchctl"
let uid = getuid()

func domainTarget() -> String { "gui/\(uid)" }
func serviceTarget(_ job: String) -> String { "gui/\(uid)/\(prefix).\(job)" }
func dashboardPlist() -> String {
    FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/LaunchAgents/\(prefix).dashboard.plist").path
}

// The launchctl argument lists. The menu actions and --self-test both use these, so --self-test prints what a click runs.
func kickstartArgs(_ job: String) -> [String] { ["kickstart", serviceTarget(job)] }
func restartDashboardArgs(loaded: Bool) -> [String] {
    // Loaded: kickstart -k kills the running instance and starts it again.
    // Not loaded (after "Ferma"): bootstrap loads the plist again; RunAtLoad starts it and KeepAlive applies again.
    loaded ? ["kickstart", "-k", serviceTarget("dashboard")] : ["bootstrap", domainTarget(), dashboardPlist()]
}
// KeepAlive would restart a killed dashboard at once, so stopping it means unloading it (bootout). It stays stopped
// until "Avvia / riavvia" or the next login, when launchd loads ~/Library/LaunchAgents again.
func stopDashboardArgs() -> [String] { ["bootout", serviceTarget("dashboard")] }
func formatCommand(_ args: [String]) -> String { ([launchctlPath] + args).joined(separator: " ") }

@discardableResult
func run(_ executable: String, _ args: [String]) -> (status: Int32, output: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = args
    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe
    do { try process.run() } catch { return (-1, "") }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()  // read before waiting: a full pipe would block launchctl
    process.waitUntilExit()
    return (process.terminationStatus, String(decoding: data, as: UTF8.self))
}

struct JobStatus {
    let running: Bool
    let runs: Int?
    let lastExit: Int?   // nil when it never exited
}

/// nil when the job is not loaded in launchd.
func jobStatus(_ job: String) -> JobStatus? {
    let result = run(launchctlPath, ["print", serviceTarget(job)])
    guard result.status == 0 else { return nil }
    func number(after key: String) -> Int? {
        for line in result.output.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix(key + " = ") {
                return Int(trimmed.dropFirst(key.count + 3).trimmingCharacters(in: .whitespaces))
            }
        }
        return nil
    }
    let running = result.output.contains("state = running")
    return JobStatus(running: running, runs: number(after: "runs"), lastExit: number(after: "last exit code"))
}

func visibleGroups() -> [[String]] {
    jobGroups.map { $0.filter { jobStatus($0) != nil } }.filter { !$0.isEmpty }
}

func checkDashboard(_ done: @escaping (Bool, String) -> Void) {
    let config = URLSessionConfiguration.ephemeral
    config.timeoutIntervalForRequest = 3
    config.timeoutIntervalForResource = 3
    config.connectionProxyDictionary = [:]
    let session = URLSession(configuration: config)
    session.dataTask(with: healthURL) { _, response, error in
        // Green only on HTTP 200: a 403 or 500 means something is wrong.
        if let http = response as? HTTPURLResponse {
            done(http.statusCode == 200, "HTTP \(http.statusCode)")
        } else {
            done(false, error.map { ($0 as NSError).localizedDescription } ?? "nessuna risposta")
        }
        session.finishTasksAndInvalidate()
    }.resume()
}

func notify(_ text: String) {
    run("/usr/bin/osascript", ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                              "-e", "end run", "Second brain", text])
}

func dotImage(_ color: NSColor) -> NSImage {
    // Drawn in code: no binary asset in the repo.
    NSImage(size: NSSize(width: 18, height: 18), flipped: false) { rect in
        color.setFill()
        NSBezierPath(ovalIn: rect.insetBy(dx: 4, dy: 4)).fill()
        return true
    }
}

// ---------------------------------------------------------------- self-test (no UI)

if CommandLine.arguments.dropFirst().first == "--self-test" {
    let semaphore = DispatchSemaphore(value: 0)
    checkDashboard { up, detail in
        print("health: GET \(healthURL.absoluteString) -> \(up ? "OK" : "NON RISPONDE") (\(detail))")
        semaphore.signal()
    }
    semaphore.wait()
    print("menu Dashboard:")
    print("  Apri dashboard -> default browser \(dashboardURL.absoluteString)")
    let loaded = jobStatus("dashboard") != nil
    print("  Avvia / riavvia -> \(formatCommand(restartDashboardArgs(loaded: loaded)))")
    print("  Ferma -> \(formatCommand(stopDashboardArgs()))")
    print("menu Avvia job:")
    let groups = visibleGroups()
    if groups.isEmpty { print("  (nessun job caricato)") }
    for group in groups {
        print("  \(group.joined(separator: " + ")) -> " + group.map { formatCommand(kickstartArgs($0)) }.joined(separator: " ; then, after it ends: "))
    }
    print("menu Notifiche: Notifiche attive (on)")
    exit(0)
}

// ---------------------------------------------------------------- menu bar

final class TrayController: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    let upImage = dotImage(.systemGreen)
    let downImage = dotImage(.systemRed)
    let jobsMenu = NSMenu(title: "Avvia job")
    let toggleItem = NSMenuItem(title: "Notifiche attive (questa sessione)", action: #selector(TrayController.toggleNotifications), keyEquivalent: "")
    var dashboardUp: Bool? = nil        // unknown until the first check: no notification for the initial state
    var notificationsOn = true
    var seenRuns: [String: Int] = [:]   // job -> "runs" value already examined
    var chain: [String] = []
    var chainCurrent: String? = nil
    var chainStarted = Date.distantPast
    var timers: [Timer] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem.button?.image = downImage
        statusItem.button?.toolTip = "Second brain: controllo in corso"
        statusItem.menu = buildMenu()
        refreshDashboard()
        checkFailures(seed: true)
        timers.append(Timer.scheduledTimer(withTimeInterval: pollSeconds, repeats: true) { [weak self] _ in
            self?.refreshDashboard()
            self?.checkFailures(seed: false)
        })
        timers.append(Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.advanceChain() })
    }

    func buildMenu() -> NSMenu {
        let menu = NSMenu()
        let dashboard = NSMenu(title: "Dashboard")
        dashboard.addItem(item("Apri dashboard", #selector(openDashboard)))
        dashboard.addItem(item("Avvia / riavvia", #selector(restartDashboard)))
        dashboard.addItem(item("Ferma (fino ad Avvia o al prossimo login)", #selector(stopDashboard)))
        menu.addItem(submenu("Dashboard", dashboard))
        jobsMenu.delegate = self   // rebuilt in menuNeedsUpdate, so a job loaded later shows up
        menu.addItem(submenu("Avvia job", jobsMenu))
        let notifications = NSMenu(title: "Notifiche")
        toggleItem.target = self
        toggleItem.state = .on
        notifications.addItem(toggleItem)
        menu.addItem(submenu("Notifiche", notifications))
        menu.addItem(.separator())
        menu.addItem(item("Esci", #selector(quit)))
        return menu
    }

    func item(_ title: String, _ action: Selector) -> NSMenuItem {
        let menuItem = NSMenuItem(title: title, action: action, keyEquivalent: "")
        menuItem.target = self
        return menuItem
    }

    func submenu(_ title: String, _ menu: NSMenu) -> NSMenuItem {
        let menuItem = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        menuItem.submenu = menu
        return menuItem
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        guard menu === jobsMenu else { return }
        menu.removeAllItems()
        let groups = visibleGroups()
        if groups.isEmpty {
            let empty = NSMenuItem(title: "(nessun job caricato)", action: nil, keyEquivalent: "")
            empty.isEnabled = false
            menu.addItem(empty)
        }
        for group in groups {
            let menuItem = item(group.joined(separator: " + "), #selector(startGroup(_:)))
            menuItem.representedObject = group   // names from the allowlist, read back in startGroup
            menu.addItem(menuItem)
        }
    }

    func say(_ text: String, always: Bool = false) {
        // Answers to a click (always) are shown even with notifications off; background events follow the toggle.
        if always || notificationsOn { notify(text) }
    }

    func refreshDashboard(expectDown: Bool = false) {
        checkDashboard { up, detail in
            DispatchQueue.main.async {
                self.statusItem.button?.image = up ? self.upImage : self.downImage
                self.statusItem.button?.toolTip = up ? "Second brain: dashboard attiva" : "Second brain: dashboard ferma"
                if let before = self.dashboardUp, before != up {
                    self.say(up ? "La dashboard risponde di nuovo." : "La dashboard non risponde (\(detail)).")
                }
                if expectDown && up { self.say("La dashboard risponde ancora dopo Ferma.", always: true) }
                self.dashboardUp = up
            }
        }
    }

    func checkFailures(seed: Bool) {
        // A run is examined once it has ended: "runs" grows when a run starts, so it is looked at only when not running.
        for job in jobGroups.joined() where !noFailureCheck.contains(job) {
            guard let status = jobStatus(job), !status.running, let runs = status.runs else { continue }
            if seenRuns[job] == runs { continue }
            seenRuns[job] = runs
            // At startup old results are only remembered, so a failure is not announced again at every login.
            if !seed, let code = status.lastExit, code != 0 {
                say("Il job \(job) è finito con un errore (codice \(code)). Vedi il suo log.")
            }
        }
    }

    @objc func openDashboard() { NSWorkspace.shared.open(dashboardURL) }

    @objc func restartDashboard() {
        let result = run(launchctlPath, restartDashboardArgs(loaded: jobStatus("dashboard") != nil))
        say(result.status == 0 ? "Dashboard avviata: l'icona diventa verde quando risponde." : "Non riesco ad avviare la dashboard.", always: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self.refreshDashboard() }
    }

    @objc func stopDashboard() {
        let result = run(launchctlPath, stopDashboardArgs())
        let ok = result.status == 0
        say(ok ? "Dashboard fermata. Riparte con Avvia / riavvia o al prossimo login." : "Non riesco a fermare la dashboard.", always: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self.refreshDashboard(expectDown: ok) }
    }

    @objc func startGroup(_ sender: NSMenuItem) {
        guard let group = sender.representedObject as? [String] else { return }
        if let current = chainCurrent {
            say("Aspetto la fine di \(current) prima di avviare altro.", always: true)
            return
        }
        say("Avvio: " + group.joined(separator: " + "), always: true)
        chain = group
        startNextInChain()
    }

    func startNextInChain() {
        guard !chain.isEmpty else { chainCurrent = nil; return }
        let job = chain.removeFirst()
        // kickstart without -k: if the job is already running it is left alone.
        if run(launchctlPath, kickstartArgs(job)).status == 0 {
            chainCurrent = job
            chainStarted = Date()
        } else {
            say("Non riesco ad avviare \(job).", always: true)
            chain = []
            chainCurrent = nil
        }
    }

    func advanceChain() {
        guard let current = chainCurrent else { return }
        let elapsed = Date().timeIntervalSince(chainStarted)
        if elapsed < 10 { return }
        if let status = jobStatus(current), status.running, elapsed < 2 * 3600 { return }
        startNextInChain()
    }

    @objc func toggleNotifications() {
        notificationsOn.toggle()
        toggleItem.state = notificationsOn ? .on : .off
    }

    @objc func quit() { NSApp.terminate(nil) }
}

// One menu-bar icon per user: an exclusive lock held for the whole life of the process.
let supportDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/\(prefix)")
try? FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
let lockFD = open(supportDir.appendingPathComponent("tray.lock").path, O_CREAT | O_RDWR, 0o600)
if lockFD < 0 || flock(lockFD, LOCK_EX | LOCK_NB) != 0 { exit(0) }

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // like LSUIElement: no Dock icon, no app menu
let controller = TrayController()
app.delegate = controller
app.run()
