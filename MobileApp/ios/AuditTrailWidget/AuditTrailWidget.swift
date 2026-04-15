import SwiftUI
import UIKit
import WidgetKit

// Must match Flutter [audit_trail_home_widget_sync.dart] and App Group entitlements.
private let kAppGroupId = "group.com.hum.databank"
private let kDataKey = "audit_trail_json"

struct AuditLine: Codable {
    let description: String
    let activity_type: String?
    let user: String
    let timestamp: String

    static let placeholder = AuditLine(
        description: "…",
        activity_type: nil,
        user: "",
        timestamp: ""
    )
    static let empty = AuditLine(
        description: "Open the app and visit Audit Trail to refresh.",
        activity_type: nil,
        user: "",
        timestamp: ""
    )
}

struct AuditTrailEntry: TimelineEntry {
    let date: Date
    let lines: [AuditLine]
}

struct AuditTrailTimelineProvider: TimelineProvider {
    func placeholder(in context: Context) -> AuditTrailEntry {
        AuditTrailEntry(date: Date(), lines: [.placeholder])
    }

    func getSnapshot(in context: Context, completion: @escaping (AuditTrailEntry) -> Void) {
        completion(AuditTrailEntry(date: Date(), lines: Self.loadLines()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<AuditTrailEntry>) -> Void) {
        let entry = AuditTrailEntry(date: Date(), lines: Self.loadLines())
        let next = Calendar.current.date(byAdding: .minute, value: 30, to: Date())!
        completion(Timeline(entries: [entry], policy: .after(next)))
    }

    fileprivate static func loadLines() -> [AuditLine] {
        guard let defaults = UserDefaults(suiteName: kAppGroupId),
              let json = defaults.string(forKey: kDataKey),
              let data = json.data(using: .utf8),
              let decoded = try? JSONDecoder().decode([AuditLine].self, from: data),
              !decoded.isEmpty
        else {
            return [.empty]
        }
        return decoded
    }
}

struct AuditTrailWidget: Widget {
    let kind: String = "AuditTrailWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: AuditTrailTimelineProvider()) { entry in
            AuditTrailEntryView(entry: entry)
                .widgetContainerBackground()
        }
        .configurationDisplayName("Audit trail")
        .description("Recent back office audit activity.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

private extension View {
    @ViewBuilder
    func widgetContainerBackground() -> some View {
        if #available(iOSApplicationExtension 17.0, *) {
            containerBackground(.fill.tertiary, for: .widget)
        } else {
            padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(UIColor.secondarySystemBackground))
        }
    }
}

struct AuditTrailEntryView: View {
    var entry: AuditTrailEntry
    @Environment(\.widgetFamily) private var family

    private var maxRows: Int {
        switch family {
        case .systemSmall: return 2
        case .systemMedium: return 4
        default: return 8
        }
    }

    private var rows: [AuditLine] {
        Array(entry.lines.prefix(maxRows))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Audit trail")
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)

            ForEach(Array(rows.enumerated()), id: \.offset) { index, line in
                VStack(alignment: .leading, spacing: 2) {
                    Text(line.description)
                        .font(family == .systemSmall ? .caption2 : .caption)
                        .fontWeight(.medium)
                        .lineLimit(family == .systemSmall ? 2 : 3)
                        .foregroundColor(.primary)

                    HStack(spacing: 6) {
                        if let act = line.activity_type, !act.isEmpty {
                            Text(act)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                        if !line.user.isEmpty {
                            Text(line.user)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }
                    if !line.timestamp.isEmpty {
                        Text(line.timestamp)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                if index < rows.count - 1 {
                    Divider()
                        .opacity(0.35)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .widgetURL(URL(string: "humdatabank://"))
    }
}
