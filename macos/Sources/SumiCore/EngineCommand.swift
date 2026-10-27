import Foundation

/// Commands understood by `sumi/service.py`.
public enum EngineCommand: Equatable, Sendable {
    public enum Action: String, Sendable {
        case restore, calibrate, confirm, toggle, virtual
    }

    case setCamera(String)
    case setEffect(String)
    case setResolution(String)
    case setHold(String)
    case setOutput(String)
    case setLeaveDelay(String)
    case setBackground(dynamic: Bool)
    case setLeave(enabled: Bool)
    case setSounds(enabled: Bool)
    case setCallSounds(enabled: Bool)
    case refreshCameras
    case startCamera
    case stopCamera
    case primary
    case engine(Action)
    case prepareMeet
    case extensionPath
    case shutdown

    /// One protocol line, without the trailing newline.
    public func line(id: Int) -> Data {
        var message: [String: Any] = ["id": id]
        switch self {
        case .setCamera(let value): message["cmd"] = "set_camera"; message["value"] = value
        case .setEffect(let value): message["cmd"] = "set_effect"; message["value"] = value
        case .setResolution(let value): message["cmd"] = "set_resolution"; message["value"] = value
        case .setHold(let value): message["cmd"] = "set_hold"; message["value"] = value
        case .setOutput(let value): message["cmd"] = "set_output"; message["value"] = value
        case .setLeaveDelay(let value): message["cmd"] = "set_leave_delay"; message["value"] = value
        case .setBackground(let dynamic): message["cmd"] = "set_background"; message["dynamic"] = dynamic
        case .setLeave(let enabled): message["cmd"] = "set_leave"; message["enabled"] = enabled
        case .setSounds(let enabled): message["cmd"] = "set_sounds"; message["enabled"] = enabled
        case .setCallSounds(let enabled): message["cmd"] = "set_call_sounds"; message["enabled"] = enabled
        case .refreshCameras: message["cmd"] = "refresh_cameras"
        case .startCamera: message["cmd"] = "start_camera"
        case .stopCamera: message["cmd"] = "stop_camera"
        case .primary: message["cmd"] = "primary"
        case .engine(let action): message["cmd"] = "engine"; message["name"] = action.rawValue
        case .prepareMeet: message["cmd"] = "prepare_meet"
        case .extensionPath: message["cmd"] = "extension_path"
        case .shutdown: message["cmd"] = "shutdown"
        }
        // Only strings, ints and bools above, so serialization cannot fail.
        return try! JSONSerialization.data(withJSONObject: message, options: [.sortedKeys])
    }
}
