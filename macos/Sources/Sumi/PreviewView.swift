import AppKit
import SumiCore
import QuartzCore
import SwiftUI

/// Live preview. A display link checks the shared buffer on every screen refresh and
/// swaps the layer contents when a newer frame exists, so frames reach the screen at
/// the camera's own pace without going through SwiftUI.
struct PreviewView: NSViewRepresentable {
    let reader: PreviewReader?
    /// False while the camera is off: the view clears and waits for a new session.
    let active: Bool

    func makeNSView(context: Context) -> PreviewLayerView { PreviewLayerView() }

    func updateNSView(_ view: PreviewLayerView, context: Context) {
        view.reduceMotion = context.environment.accessibilityReduceMotion
        view.update(reader: active ? reader : nil)
    }
}

final class PreviewLayerView: NSView {
    var reduceMotion = false
    private var reader: PreviewReader?
    private var shown = Int.min
    private var link: CADisplayLink?

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.contentsGravity = .resizeAspect
        layer?.backgroundColor = NSColor.clear.cgColor
        layer?.opacity = 0
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not used") }

    override var isFlipped: Bool { true }

    func update(reader: PreviewReader?) {
        guard reader !== self.reader else { return }
        self.reader = reader
        if reader == nil { clear() }
        updateLink()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        updateLink()
    }

    /// Runs only while there is something to show, so an idle window costs nothing.
    private func updateLink() {
        let wanted = window != nil && reader != nil
        if wanted, link == nil {
            let link = displayLink(target: self, selector: #selector(step))
            link.add(to: .main, forMode: .common)
            self.link = link
        } else if !wanted, let link {
            link.invalidate()
            self.link = nil
        }
    }

    @objc private func step(_ link: CADisplayLink) {
        guard let layer, let frame = reader?.latest(after: shown) else { return }
        let first = shown == .min
        shown = frame.revision
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        layer.contents = frame.image
        CATransaction.commit()
        if first { fade(to: 1, duration: 0.35) }
    }

    private func clear() {
        shown = .min
        fade(to: 0, duration: 0.2)
    }

    private func fade(to opacity: Float, duration: CFTimeInterval) {
        guard let layer else { return }
        let animation = CABasicAnimation(keyPath: "opacity")
        animation.fromValue = layer.presentation()?.opacity ?? layer.opacity
        animation.toValue = opacity
        animation.duration = reduceMotion ? 0 : duration
        animation.timingFunction = CAMediaTimingFunction(name: .easeOut)
        layer.opacity = opacity
        layer.add(animation, forKey: "fade")
        guard opacity == 0 else { return }
        // Drop the last frame after the fade so a new session never flashes it.
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(duration))
            if let self, self.reader == nil { self.layer?.contents = nil }
        }
    }
}

/// Gesture illustrations from `assets/gestures`, loaded once each.
enum GuideImages {
    private static var cache: [URL: NSImage] = [:]

    static func image(named name: String, in resources: URL?) -> NSImage? {
        guard let resources, !name.isEmpty else { return nil }
        let url = resources.appending(path: "assets/gestures/\(name)")
        if let cached = cache[url] { return cached }
        let image = NSImage(contentsOf: url)
        cache[url] = image
        return image
    }
}
