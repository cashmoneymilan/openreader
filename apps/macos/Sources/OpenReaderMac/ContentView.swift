import SwiftUI
import UniformTypeIdentifiers

private enum WorkflowState {
    case waiting
    case active
    case complete
}

struct ContentView: View {
    @EnvironmentObject private var model: AppModel
    @State private var isDropTargeted = false

    var body: some View {
        HStack(spacing: 0) {
            sidebar
                .frame(width: 245)
            Divider()
            detail
        }
        .toolbar { toolbarContent }
        .fileImporter(
            isPresented: $model.requestFilePicker,
            allowedContentTypes: [.pdf],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                model.choose(url)
            }
        }
        .onChange(of: model.deviceKind) { _, kind in
            model.updateDeviceKind(kind)
        }
    }

    private var sidebar: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("WORKFLOW")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    VStack(spacing: 8) {
                    workflowRow(
                        title: "Source",
                        detail: model.selectedPDF == nil ? "Choose a PDF" : "Original preserved",
                        symbol: "doc",
                        state: model.selectedPDF == nil ? .waiting : .complete
                    )
                    workflowRow(
                        title: "EPUB",
                        detail: model.conversion == nil ? "Not created" : "Reader profile applied",
                        symbol: "book.closed",
                        state: conversionState
                    )
                    workflowRow(
                        title: "Validation",
                        detail: validationDetail,
                        symbol: "checkmark.seal",
                        state: validationState
                    )
                    workflowRow(
                        title: "Reader",
                        detail: model.transfer == nil ? "Not sent" : userEvidence(model.transfer?.evidence ?? "unknown"),
                        symbol: "rectangle.portrait.and.arrow.right",
                        state: transferState
                    )
                    }

                    Divider()

                    Text("READER PROFILE")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)

                    VStack(spacing: 9) {
                        sidebarValue("Device", "Xteink X4")
                        sidebarValue("Format", "EPUB 2")
                        sidebarValue("Image limit", "1000 px")
                    }
                }
                .padding(14)
            }

            Divider()

            HStack(spacing: 10) {
                Image(systemName: engineSymbol)
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(engineColor)
                VStack(alignment: .leading, spacing: 1) {
                    Text(model.engine.state.label)
                        .font(.callout.weight(.medium))
                    Text("Runs locally on this Mac")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(14)
        }
        .background(.regularMaterial)
    }

    private var detail: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
                .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    pageHeader
                    sourceCard

                    if let conversion = model.conversion {
                        conversionReceipt(conversion)
                        deviceCard
                    }

                    if case .failed(let message) = model.phase {
                        errorBanner(message)
                    }
                }
                .frame(maxWidth: 860, alignment: .leading)
                .padding(28)
                .frame(maxWidth: .infinity, alignment: .top)
            }
        }
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .automatic) {
            Label(model.engine.state.label, systemImage: engineSymbol)
                .foregroundStyle(engineColor)
                .help("The private conversion engine runs only while OpenReader is open.")
        }

        ToolbarItemGroup(placement: .primaryAction) {
            Button {
                model.requestFilePicker = true
            } label: {
                Label("Choose PDF", systemImage: "doc.badge.plus")
            }
            .help("Choose a PDF")

            Button {
                Task { await model.convert() }
            } label: {
                if model.phase == .converting {
                    ProgressView()
                        .controlSize(.small)
                } else {
                    Label("Create EPUB", systemImage: "wand.and.stars")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!canConvert)
            .help("Create and validate an EPUB for Xteink readers")
        }
    }

    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(model.conversion == nil ? "Create an EPUB" : "EPUB ready")
                .font(.largeTitle.weight(.semibold))
            Text(model.conversion == nil
                 ? "Convert a PDF into a validated, reader-friendly book."
                 : "Review the conversion receipt, then send the book to your reader.")
                .font(.body)
                .foregroundStyle(.secondary)
        }
    }

    private var sourceCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Source PDF", systemImage: "doc.text")
                .font(.headline)

            HStack(spacing: 16) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color.accentColor.opacity(model.selectedPDF == nil ? 0.08 : 0.13))
                    Image(systemName: model.selectedPDF == nil ? "doc.badge.plus" : "doc.richtext.fill")
                        .font(.system(size: 28, weight: .regular))
                        .symbolRenderingMode(.hierarchical)
                        .foregroundStyle(model.selectedPDF == nil ? .secondary : Color.accentColor)
                }
                .frame(width: 58, height: 66)

                VStack(alignment: .leading, spacing: 4) {
                    Text(model.selectedPDF?.lastPathComponent ?? "Drop a PDF here")
                        .font(.headline)
                        .lineLimit(1)
                    Text(sourceDetail)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer(minLength: 16)

                Button(model.selectedPDF == nil ? "Choose PDF…" : "Replace…") {
                    model.requestFilePicker = true
                }
                .buttonStyle(.bordered)

                Button {
                    Task { await model.convert() }
                } label: {
                    if model.phase == .converting {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Text("Create EPUB")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canConvert)
            }
            .padding(6)
            .frame(minHeight: 82)
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(isDropTargeted ? Color.accentColor : Color(nsColor: .separatorColor), lineWidth: isDropTargeted ? 2 : 0.5)
        }
        .dropDestination(for: URL.self) { urls, _ in
            guard let first = urls.first else { return false }
            model.choose(first)
            return true
        } isTargeted: {
            isDropTargeted = $0
        }
    }

    private func conversionReceipt(_ report: ConversionReport) -> some View {
        nativeCard("Conversion receipt", systemImage: "doc.text.magnifyingglass") {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .center) {
                    Label(
                        report.validation.valid ? "Ready for your reader" : "Review required",
                        systemImage: report.validation.valid ? "checkmark.circle.fill" : "exclamationmark.triangle.fill"
                    )
                    .font(.headline)
                    .foregroundStyle(report.validation.valid ? .green : .orange)

                    Spacer()

                    Text("Tier \(report.supportTier)")
                        .font(.callout.weight(.medium))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 4)
                        .background(.quaternary, in: Capsule())
                }

                Divider()

                Grid(alignment: .leading, horizontalSpacing: 32, verticalSpacing: 8) {
                    GridRow {
                        receiptMetric("Conversion", report.mode == "reflow" ? "Reflow" : "Page images", report.tierReasons.first ?? "Inspected")
                        receiptMetric("Text retained", retentionLabel(report.normalizedTextRetention), "Normalized comparison")
                        receiptMetric("Package", "EPUB \(report.validation.packageVersion ?? "2")", "\(report.validation.chapters) sections")
                        receiptMetric("Source", "\(report.pages) pages", report.validation.valid ? "Validation passed" : "Needs review")
                    }
                }

                Divider()

                LabeledContent("Output") {
                    Text(URL(fileURLWithPath: report.output).lastPathComponent)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                HStack {
                    if !report.validation.issues.isEmpty {
                        Label("\(report.validation.issues.count) validation notes", systemImage: "info.circle")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Open Preview") { model.openPreview() }
                    Button("Show in Finder") { model.revealEPUB() }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
    }

    private var deviceCard: some View {
        nativeCard("Send to reader", systemImage: "wifi") {
            VStack(alignment: .leading, spacing: 16) {
                Picker("Firmware", selection: $model.deviceKind) {
                    ForEach(DeviceKind.allCases) { kind in
                        Text(kind.label).tag(kind)
                    }
                }
                .pickerStyle(.segmented)

                Divider()

                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 12) {
                    GridRow {
                        Text("Device address")
                            .foregroundStyle(.secondary)
                        TextField("http://crosspoint.local", text: $model.deviceURL)
                            .textFieldStyle(.roundedBorder)
                    }
                    GridRow {
                        Text("Destination")
                            .foregroundStyle(.secondary)
                        TextField("/Books", text: $model.deviceFolder)
                            .textFieldStyle(.roundedBorder)
                    }
                }

                HStack(spacing: 10) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .symbolRenderingMode(.hierarchical)
                        .foregroundStyle(Color.accentColor)
                    Text(model.probeMessage)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button(model.phase == .probing ? "Checking…" : "Check Connection") {
                        Task { await model.probe() }
                    }
                    .disabled(model.phase == .probing || model.phase == .sending)

                    Button(model.phase == .sending ? "Sending…" : "Send EPUB") {
                        Task { await model.send() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.phase == .probing || model.phase == .sending)
                }

                if let transfer = model.transfer {
                    evidenceReceipt(transfer)
                }
            }
        }
    }

    private func evidenceReceipt(_ report: TransferReport) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: report.evidence == "verified_readback" ? "checkmark.shield.fill" : "checkmark.circle.fill")
                .font(.title2)
                .foregroundStyle(.green)

            VStack(alignment: .leading, spacing: 3) {
                Text(userEvidence(report.evidence))
                    .font(.headline)
                Text(report.observations.joined(separator: " • "))
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Text(report.destination)
                .font(.callout.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(12)
        .background(Color.green.opacity(0.09), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
            Text(message)
                .textSelection(.enabled)
            Spacer()
        }
        .padding(12)
        .background(Color.red.opacity(0.09), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func workflowRow(
        title: String,
        detail: String,
        symbol: String,
        state: WorkflowState
    ) -> some View {
        HStack(spacing: 10) {
            Image(systemName: workflowSymbol(symbol, state: state))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(workflowColor(state))
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()
        }
        .padding(.vertical, 3)
    }

    private func sidebarValue(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .fontWeight(.medium)
        }
        .font(.caption)
        .padding(.horizontal, 4)
    }

    private func nativeCard<Content: View>(
        _ title: String,
        systemImage: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(title, systemImage: systemImage)
                .font(.headline)
            Divider()
            content()
        }
        .padding(14)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
        }
    }

    private func receiptMetric(_ label: String, _ value: String, _ note: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold))
                .monospacedDigit()
            Text(note)
                .font(.caption)
                .foregroundStyle(.tertiary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var canConvert: Bool {
        model.selectedPDF != nil && model.phase != .converting && model.engine.state == .ready
    }

    private var sourceDetail: String {
        guard let selectedPDF = model.selectedPDF else {
            return "or click Choose PDF to begin"
        }
        return selectedPDF.deletingLastPathComponent().path
    }

    private var conversionState: WorkflowState {
        if model.conversion != nil { return .complete }
        return model.phase == .converting ? .active : .waiting
    }

    private var validationState: WorkflowState {
        if model.conversion?.validation.valid == true { return .complete }
        return model.phase == .converting ? .active : .waiting
    }

    private var transferState: WorkflowState {
        if model.transfer != nil { return .complete }
        return model.phase == .sending ? .active : .waiting
    }

    private var validationDetail: String {
        if model.conversion?.validation.valid == true { return "Package passed" }
        return model.phase == .converting ? "Checking package" : "Not checked"
    }

    private var engineSymbol: String {
        switch model.engine.state {
        case .ready: return "checkmark.circle.fill"
        case .starting: return "clock.fill"
        case .stopped: return "stop.circle.fill"
        case .failed: return "exclamationmark.triangle.fill"
        }
    }

    private var engineColor: Color {
        switch model.engine.state {
        case .ready: return .green
        case .starting: return .orange
        case .stopped, .failed: return .red
        }
    }

    private func workflowSymbol(_ fallback: String, state: WorkflowState) -> String {
        switch state {
        case .waiting: return fallback
        case .active: return "clock.fill"
        case .complete: return "checkmark.circle.fill"
        }
    }

    private func workflowColor(_ state: WorkflowState) -> Color {
        switch state {
        case .waiting: return .secondary
        case .active: return .orange
        case .complete: return .green
        }
    }

    private func retentionLabel(_ value: Double?) -> String {
        guard let value else { return "Layout kept" }
        return value.formatted(.percent.precision(.fractionLength(1)))
    }

    private func userEvidence(_ evidence: String) -> String {
        switch evidence {
        case "verified_readback", "listed_on_device": return "On device"
        case "upload_acknowledged", "sent_unverified": return "Sent, not fully verified"
        case "staged": return "Ready to transfer"
        case "failed": return "Transfer failed"
        default: return "Could not verify"
        }
    }
}
