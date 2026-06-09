import EventKit
import Foundation

let args = CommandLine.arguments
let mode = args.count > 1 ? args[1] : "today"
let payloadPath = args.count > 3 ? args[2] : ""
let outputPath = args.count > 2 ? (args.last ?? "") : ""

enum AccessKind {
    case events
    case reminders
}

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

func loadPayload() -> [String: Any] {
    guard !payloadPath.isEmpty else { return [:] }
    let url = URL(fileURLWithPath: payloadPath)
    guard let data = try? Data(contentsOf: url) else { return [:] }
    guard let object = try? JSONSerialization.jsonObject(with: data, options: []),
          let dict = object as? [String: Any] else {
        return [:]
    }
    return dict
}

func stringValue(_ value: Any?) -> String {
    if let text = value as? String {
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return ""
}

func normalizedMatchText(_ value: String) -> String {
    value
        .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
}

func intValue(_ value: Any?, default fallback: Int) -> Int {
    if let number = value as? Int {
        return number
    }
    if let number = value as? Double {
        return Int(number)
    }
    if let text = value as? String, let number = Int(text) {
        return number
    }
    return fallback
}

func boolValue(_ value: Any?) -> Bool {
    if let flag = value as? Bool {
        return flag
    }
    if let number = value as? Int {
        return number != 0
    }
    if let text = value as? String {
        switch text.lowercased() {
        case "1", "true", "yes", "evet":
            return true
        default:
            return false
        }
    }
    return false
}

func parseDate(_ text: String) -> Date? {
    let raw = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !raw.isEmpty else { return nil }

    let iso = ISO8601DateFormatter()
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = iso.date(from: raw) {
        return date
    }
    iso.formatOptions = [.withInternetDateTime]
    if let date = iso.date(from: raw) {
        return date
    }

    let formatters = [
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd'T'HH:mm",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd HH:mm",
        "dd.MM.yyyy HH:mm",
        "yyyy-MM-dd",
        "dd.MM.yyyy",
    ]
    for format in formatters {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = format
        if let date = formatter.date(from: raw) {
            return date
        }
    }
    return nil
}

func accessKind(for mode: String) -> AccessKind {
    if mode.hasPrefix("reminders") || mode == "create_reminder" {
        return .reminders
    }
    return .events
}

func dueTimestamp(for reminder: EKReminder) -> Int {
    guard let dueDate = reminder.dueDateComponents?.date else {
        return 0
    }
    return Int(dueDate.timeIntervalSince1970)
}

func serializeEvent(_ event: EKEvent) -> [String: Any] {
    [
        "start_ts": Int(event.startDate.timeIntervalSince1970),
        "end_ts": Int(event.endDate.timeIntervalSince1970),
        "calendar": event.calendar.title,
        "title": event.title ?? "Adsiz etkinlik",
        "location": event.location ?? "",
        "notes": event.notes ?? "",
        "all_day": event.isAllDay,
    ]
}

func serializeReminder(_ reminder: EKReminder) -> [String: Any] {
    [
        "title": reminder.title ?? "Adsiz animsatici",
        "list_name": reminder.calendar.title,
        "notes": reminder.notes ?? "",
        "completed": reminder.isCompleted,
        "priority": reminder.priority,
        "due_ts": dueTimestamp(for: reminder),
        "all_day": reminder.dueDateComponents?.hour == nil && reminder.dueDateComponents?.minute == nil,
    ]
}

let payload = loadPayload()
let store = EKEventStore()
let sem = DispatchSemaphore(value: 0)

var granted = false
var timedOut = false
var errorMessage = ""

switch accessKind(for: mode) {
case .events:
    if #available(macOS 14.0, *) {
        store.requestFullAccessToEvents { ok, error in
            granted = ok
            if let error { errorMessage = error.localizedDescription }
            sem.signal()
        }
    } else {
        store.requestAccess(to: .event) { ok, error in
            granted = ok
            if let error { errorMessage = error.localizedDescription }
            sem.signal()
        }
    }
case .reminders:
    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { ok, error in
            granted = ok
            if let error { errorMessage = error.localizedDescription }
            sem.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { ok, error in
            granted = ok
            if let error { errorMessage = error.localizedDescription }
            sem.signal()
        }
    }
}

if sem.wait(timeout: .now() + 8) == .timedOut {
    timedOut = true
}

if timedOut {
    emit([
        "ok": false,
        "error": "timeout",
        "detail": "Organizer izin istegi zaman asimina ugradi.",
    ])
    exit(0)
}

if !granted {
    emit([
        "ok": false,
        "error": "permission_denied",
        "detail": errorMessage,
    ])
    exit(0)
}

func runCalendarEvents() {
    let cal = Calendar.current
    let now = Date()
    var start = now
    var end = now

    switch mode {
    case "tomorrow":
        let todayStart = cal.startOfDay(for: now)
        start = cal.date(byAdding: .day, value: 1, to: todayStart) ?? todayStart
        end = cal.date(byAdding: .day, value: 1, to: start) ?? start
    case "week":
        start = cal.startOfDay(for: now)
        end = cal.date(byAdding: .day, value: 7, to: start) ?? start
    case "next":
        start = now
        end = cal.date(byAdding: .day, value: 30, to: now) ?? now
    case "agenda":
        start = now
        end = cal.date(byAdding: .day, value: 3, to: now) ?? now
    default:
        start = cal.startOfDay(for: now)
        end = cal.date(byAdding: .day, value: 1, to: start) ?? start
    }

    let calendars = store.calendars(for: .event)
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
    let events = store.events(matching: predicate).sorted {
        $0.startDate < $1.startDate
    }

    let payloadEvents: [[String: Any]] = events.map(serializeEvent)

    emit([
        "ok": true,
        "events": payloadEvents,
    ])
}

func runCalendarRange() {
    let startISO = stringValue(payload["start_iso"])
    let endISO = stringValue(payload["end_iso"])

    guard let start = parseDate(startISO), let end = parseDate(endISO) else {
        emit([
            "ok": false,
            "error": "invalid_range",
            "detail": "Takvim tarih araligi gecersiz.",
        ])
        return
    }

    guard end > start else {
        emit([
            "ok": false,
            "error": "invalid_range",
            "detail": "Takvim bitis tarihi baslangictan sonra olmali.",
        ])
        return
    }

    let calendars = store.calendars(for: .event)
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
    let events = store.events(matching: predicate).sorted {
        $0.startDate < $1.startDate
    }

    let payloadEvents: [[String: Any]] = events.map(serializeEvent)
    emit([
        "ok": true,
        "events": payloadEvents,
    ])
}

func matchingEventCalendars(calendarName: String) -> [EKCalendar] {
    let calendars = store.calendars(for: .event)
    guard !calendarName.isEmpty else { return calendars }

    let exact = calendars.filter { calendar in
        calendar.title.compare(calendarName, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
    }
    if !exact.isEmpty {
        return exact
    }

    let partial = calendars.filter { calendar in
        calendar.title.range(of: calendarName, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
    return partial
}

func eventCalendarForCreation(calendarName: String) -> EKCalendar? {
    let calendars = matchingEventCalendars(calendarName: calendarName)
    if let first = calendars.first {
        return first
    }
    return store.defaultCalendarForNewEvents ?? store.calendars(for: .event).first
}

func runCreateEvent() {
    let title = stringValue(payload["title"])
    guard !title.isEmpty else {
        emit([
            "ok": false,
            "error": "missing_title",
            "detail": "Etkinlik basligi bos olamaz.",
        ])
        return
    }

    let startISO = stringValue(payload["start_iso"])
    guard let parsedStart = parseDate(startISO) else {
        emit([
            "ok": false,
            "error": "invalid_start_date",
            "detail": "Etkinlik baslangic tarihi gecersiz.",
        ])
        return
    }

    let calendarName = stringValue(payload["calendar_name"])
    guard let calendar = eventCalendarForCreation(calendarName: calendarName) else {
        emit([
            "ok": false,
            "error": "missing_calendar",
            "detail": "Takvim bulunamadi.",
        ])
        return
    }

    let allDay = boolValue(payload["all_day"]) || startISO.count == 10
    let cal = Calendar.current
    let startDate: Date
    let endDate: Date

    if allDay {
        let normalizedStart = cal.startOfDay(for: parsedStart)
        startDate = normalizedStart
        let endISO = stringValue(payload["end_iso"])
        if !endISO.isEmpty, let explicitEnd = parseDate(endISO) {
            let normalizedEnd = cal.startOfDay(for: explicitEnd)
            endDate = normalizedEnd > normalizedStart
                ? normalizedEnd
                : (cal.date(byAdding: .day, value: 1, to: normalizedStart) ?? normalizedStart.addingTimeInterval(86400))
        } else {
            endDate = cal.date(byAdding: .day, value: 1, to: normalizedStart) ?? normalizedStart.addingTimeInterval(86400)
        }
    } else {
        startDate = parsedStart
        let endISO = stringValue(payload["end_iso"])
        if !endISO.isEmpty {
            guard let parsedEnd = parseDate(endISO) else {
                emit([
                    "ok": false,
                    "error": "invalid_end_date",
                    "detail": "Etkinlik bitis tarihi gecersiz.",
                ])
                return
            }
            endDate = parsedEnd
        } else {
            endDate = parsedStart.addingTimeInterval(3600)
        }
    }

    if endDate <= startDate {
        emit([
            "ok": false,
            "error": "invalid_range",
            "detail": "Etkinlik bitis tarihi baslangictan sonra olmali.",
        ])
        return
    }

    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = title
    event.startDate = startDate
    event.endDate = endDate
    event.isAllDay = allDay

    let location = stringValue(payload["location"])
    if !location.isEmpty {
        event.location = location
    }

    let notes = stringValue(payload["notes"])
    if !notes.isEmpty {
        event.notes = notes
    }

    do {
        try store.save(event, span: .thisEvent, commit: true)
        emit([
            "ok": true,
            "created": serializeEvent(event),
        ])
    } catch {
        emit([
            "ok": false,
            "error": "save_failed",
            "detail": error.localizedDescription,
        ])
    }
}

func runDeleteEvent() {
    let title = stringValue(payload["title"])
    guard !title.isEmpty else {
        emit([
            "ok": false,
            "error": "missing_title",
            "detail": "Silinecek etkinlik basligi bos olamaz.",
        ])
        return
    }

    let calendarName = stringValue(payload["calendar_name"])
    let calendars = matchingEventCalendars(calendarName: calendarName)
    guard !calendars.isEmpty else {
        emit([
            "ok": false,
            "error": "missing_calendar",
            "detail": "Takvim bulunamadi.",
        ])
        return
    }

    let cal = Calendar.current
    let now = Date()
    let startISO = stringValue(payload["start_iso"])
    let deleteAllMatches = boolValue(payload["delete_all_matches"])

    let rangeStart: Date
    let rangeEnd: Date
    if let parsedStart = parseDate(startISO), !startISO.isEmpty {
        let startOfDay = cal.startOfDay(for: parsedStart)
        rangeStart = startOfDay
        rangeEnd = cal.date(byAdding: .day, value: 1, to: startOfDay) ?? startOfDay.addingTimeInterval(86400)
    } else {
        rangeStart = cal.date(byAdding: .day, value: -30, to: now) ?? now.addingTimeInterval(-30 * 86400)
        rangeEnd = cal.date(byAdding: .day, value: 365, to: now) ?? now.addingTimeInterval(365 * 86400)
    }

    let predicate = store.predicateForEvents(withStart: rangeStart, end: rangeEnd, calendars: calendars)
    let events = store.events(matching: predicate).sorted { lhs, rhs in
        lhs.startDate < rhs.startDate
    }

    let normalizedTitle = normalizedMatchText(title)
    let exactMatches = events.filter { event in
        normalizedMatchText(event.title ?? "") == normalizedTitle
    }
    let partialMatches = events.filter { event in
        normalizedMatchText(event.title ?? "").contains(normalizedTitle)
    }
    let matched = exactMatches.isEmpty ? partialMatches : exactMatches

    if matched.isEmpty {
        emit([
            "ok": false,
            "error": "not_found",
            "detail": "Silinecek etkinligi bulamadim.",
        ])
        return
    }

    if matched.count > 1 && !deleteAllMatches {
        emit([
            "ok": false,
            "error": "multiple_matches",
            "detail": "Ayni ada sahip birden fazla etkinlik buldum. Tarih veya saat belirtirsen dogru kaydi silebilirim.",
            "matches": matched.prefix(5).map(serializeEvent),
        ])
        return
    }

    let targets: [EKEvent] = deleteAllMatches ? matched : [matched[0]]
    var deletedPayloads: [[String: Any]] = []

    do {
        for event in targets {
            deletedPayloads.append(serializeEvent(event))
            try store.remove(event, span: .thisEvent, commit: false)
        }
        try store.commit()
    } catch {
        emit([
            "ok": false,
            "error": "delete_failed",
            "detail": error.localizedDescription,
        ])
        return
    }

    emit([
        "ok": true,
        "deleted": deletedPayloads.first ?? [:],
        "deleted_count": deletedPayloads.count,
        "deleted_items": deletedPayloads,
    ])
}

func matchingReminderCalendars(listName: String) -> [EKCalendar] {
    let calendars = store.calendars(for: .reminder)
    guard !listName.isEmpty else { return calendars }

    let exact = calendars.filter { calendar in
        calendar.title.compare(listName, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
    }
    if !exact.isEmpty {
        return exact
    }

    let partial = calendars.filter { calendar in
        calendar.title.range(of: listName, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }
    return partial
}

func fetchReminders(predicate: NSPredicate) -> (Bool, [EKReminder], String) {
    let fetchSem = DispatchSemaphore(value: 0)
    var reminders: [EKReminder] = []
    var fetchTimedOut = false

    store.fetchReminders(matching: predicate) { items in
        reminders = items ?? []
        fetchSem.signal()
    }

    if fetchSem.wait(timeout: .now() + 8) == .timedOut {
        fetchTimedOut = true
    }

    if fetchTimedOut {
        return (false, [], "Animsatici istegi zaman asimina ugradi.")
    }
    return (true, reminders, "")
}

func runReminderList() {
    let query = stringValue(payload["query"]).lowercased().isEmpty ? "upcoming" : stringValue(payload["query"]).lowercased()
    let limit = max(1, min(20, intValue(payload["limit"], default: 8)))
    let listName = stringValue(payload["list_name"])
    let calendars = matchingReminderCalendars(listName: listName)
    let calendarFilter = calendars.isEmpty ? store.calendars(for: .reminder) : calendars
    let now = Date()
    let cal = Calendar.current
    let startOfToday = cal.startOfDay(for: now)
    let tomorrow = cal.date(byAdding: .day, value: 1, to: startOfToday) ?? startOfToday
    let weekAhead = cal.date(byAdding: .day, value: 7, to: now) ?? now
    let monthAhead = cal.date(byAdding: .day, value: 30, to: now) ?? now

    let predicate: NSPredicate
    switch query {
    case "today":
        predicate = store.predicateForIncompleteReminders(withDueDateStarting: startOfToday, ending: tomorrow, calendars: calendarFilter)
    case "overdue":
        predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: now, calendars: calendarFilter)
    case "next":
        predicate = store.predicateForIncompleteReminders(withDueDateStarting: now, ending: monthAhead, calendars: calendarFilter)
    case "all":
        predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: calendarFilter)
    default:
        predicate = store.predicateForIncompleteReminders(withDueDateStarting: now, ending: weekAhead, calendars: calendarFilter)
    }

    let (ok, reminders, detail) = fetchReminders(predicate: predicate)
    guard ok else {
        emit([
            "ok": false,
            "error": "fetch_failed",
            "detail": detail,
        ])
        return
    }

    var filtered = reminders.filter { !$0.isCompleted }
    if query == "today" {
        filtered = filtered.filter { reminder in
            guard let dueDate = reminder.dueDateComponents?.date else { return false }
            return dueDate >= startOfToday && dueDate < tomorrow
        }
    } else if query == "overdue" {
        filtered = filtered.filter { reminder in
            guard let dueDate = reminder.dueDateComponents?.date else { return false }
            return dueDate < now
        }
    } else if query == "upcoming" {
        filtered = filtered.filter { reminder in
            guard let dueDate = reminder.dueDateComponents?.date else { return false }
            return dueDate >= now && dueDate <= weekAhead
        }
    } else if query == "next" {
        filtered = filtered.filter { reminder in
            guard let dueDate = reminder.dueDateComponents?.date else { return false }
            return dueDate >= now
        }
    }

    filtered.sort { lhs, rhs in
        let lhsTs = dueTimestamp(for: lhs)
        let rhsTs = dueTimestamp(for: rhs)
        if lhsTs == 0 && rhsTs == 0 {
            return (lhs.title ?? "") < (rhs.title ?? "")
        }
        if lhsTs == 0 { return false }
        if rhsTs == 0 { return true }
        if lhsTs == rhsTs {
            return (lhs.title ?? "") < (rhs.title ?? "")
        }
        return lhsTs < rhsTs
    }

    let finalLimit = query == "next" ? 1 : limit
    let payloadReminders = Array(filtered.prefix(finalLimit)).map(serializeReminder)
    emit([
        "ok": true,
        "reminders": payloadReminders,
    ])
}

func normalizedPriority(_ value: Any?) -> Int {
    if let number = value as? Int {
        if number == 1 || number == 5 || number == 9 || number == 0 {
            return number
        }
    }

    let text = stringValue(value).lowercased()
    switch text {
    case "high", "yuksek", "yüksek", "important", "onemli", "önemli":
        return 1
    case "medium", "orta", "normal":
        return 5
    case "low", "dusuk", "düşük":
        return 9
    default:
        return 0
    }
}

func reminderCalendarForCreation(listName: String) -> EKCalendar? {
    let calendars = matchingReminderCalendars(listName: listName)
    if let first = calendars.first {
        return first
    }
    return store.defaultCalendarForNewReminders() ?? store.calendars(for: .reminder).first
}

func runCreateReminder() {
    let title = stringValue(payload["title"])
    guard !title.isEmpty else {
        emit([
            "ok": false,
            "error": "missing_title",
            "detail": "Animsatici basligi bos olamaz.",
        ])
        return
    }

    let listName = stringValue(payload["list_name"])
    guard let calendar = reminderCalendarForCreation(listName: listName) else {
        emit([
            "ok": false,
            "error": "missing_calendar",
            "detail": "Animsatici listesi bulunamadi.",
        ])
        return
    }

    let reminder = EKReminder(eventStore: store)
    reminder.calendar = calendar
    reminder.title = title

    let notes = stringValue(payload["notes"])
    if !notes.isEmpty {
        reminder.notes = notes
    }

    let priority = normalizedPriority(payload["priority"])
    if priority > 0 {
        reminder.priority = priority
    }

    let dueISO = stringValue(payload["due_iso"])
    let allDay = boolValue(payload["all_day"]) || dueISO.count == 10
    if !dueISO.isEmpty {
        guard let dueDate = parseDate(dueISO) else {
            emit([
                "ok": false,
                "error": "invalid_due_date",
                "detail": "Animsatici tarihi gecersiz.",
            ])
            return
        }

        var comps: DateComponents
        if allDay {
            comps = Calendar.current.dateComponents([.year, .month, .day], from: dueDate)
        } else {
            comps = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: dueDate)
        }
        comps.calendar = Calendar.current
        comps.timeZone = TimeZone.current
        reminder.dueDateComponents = comps
    }

    do {
        try store.save(reminder, commit: true)
        emit([
            "ok": true,
            "created": serializeReminder(reminder),
        ])
    } catch {
        emit([
            "ok": false,
            "error": "save_failed",
            "detail": error.localizedDescription,
        ])
    }
}

switch mode {
case "today", "tomorrow", "week", "next", "agenda":
    runCalendarEvents()
case "range":
    runCalendarRange()
case "create_event":
    runCreateEvent()
case "delete_event":
    runDeleteEvent()
case "reminders_list":
    runReminderList()
case "create_reminder":
    runCreateReminder()
default:
    emit([
        "ok": false,
        "error": "unknown_mode",
        "detail": "Bilinmeyen helper modu.",
    ])
}
