import Carbon.HIToolbox

/// Global shortcuts through Carbon hot keys: they work in any app and need no
/// Accessibility permission, unlike an event tap.
final class HotKeys {
    private let action: () -> Void
    private var handler: EventHandlerRef?
    private var keys: [EventHotKeyRef] = []

    init(action: @escaping () -> Void) {
        self.action = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let context = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(GetApplicationEventTarget(), { _, _, context in
            guard let context else { return OSStatus(eventNotHandledErr) }
            // Carbon delivers hot keys on the main thread.
            MainActor.assumeIsolated {
                Unmanaged<HotKeys>.fromOpaque(context).takeUnretainedValue().action()
            }
            return noErr
        }, 1, &spec, context, &handler)
        register(key: kVK_F8, modifiers: 0, id: 1)
        register(key: kVK_ANSI_R, modifiers: controlKey | optionKey, id: 2)
    }

    isolated deinit {
        keys.forEach { UnregisterEventHotKey($0) }
        if let handler { RemoveEventHandler(handler) }
    }

    private func register(key: Int, modifiers: Int, id: UInt32) {
        var reference: EventHotKeyRef?
        let identifier = EventHotKeyID(signature: OSType(0x5355_4D49), id: id) // "SUMI"
        let status = RegisterEventHotKey(UInt32(key), UInt32(modifiers), identifier,
                                         GetApplicationEventTarget(), 0, &reference)
        if status == noErr, let reference { keys.append(reference) }
    }
}
