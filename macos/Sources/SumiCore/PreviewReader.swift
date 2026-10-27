import CoreGraphics
import Darwin
import Foundation
import Synchronization

/// Reads the double-buffered BGRA preview that `service.PreviewBuffer` writes.
///
/// Each slot starts with a sequence number that is odd while Python writes it. A frame is
/// accepted only when the sequence is even and unchanged after copying the pixels.
public final class PreviewReader {
    public enum ReadError: Error, Equatable {
        case open(Int32), map(Int32), layout(String)
    }

    private static let magic = Array("SUMIPRV1".utf8)

    public let layout: PreviewLayout
    private let base: UnsafeRawPointer
    private let length: Int

    public init(layout: PreviewLayout) throws(ReadError) {
        let descriptor = open(layout.path, O_RDONLY)
        guard descriptor >= 0 else { throw .open(errno) }
        defer { close(descriptor) }
        let expected = layout.headerBytes + layout.slots * layout.slotBytes
        var info = stat()
        guard fstat(descriptor, &info) == 0, Int(info.st_size) >= expected else {
            throw .layout("Arquivo da prévia menor que o esperado.")
        }
        guard let pointer = mmap(nil, expected, PROT_READ, MAP_SHARED, descriptor, 0),
              pointer != MAP_FAILED else { throw .map(errno) }
        let bytes = UnsafeRawPointer(pointer)
        let header = UnsafeRawBufferPointer(start: bytes, count: 8)
        guard Array(header) == Self.magic, layout.format == "bgra" else {
            munmap(pointer, expected)
            throw .layout("Formato da prévia desconhecido.")
        }
        self.layout = layout
        self.base = bytes
        self.length = expected
    }

    isolated deinit {
        munmap(UnsafeMutableRawPointer(mutating: base), length)
    }

    /// The newest complete frame with a revision above `revision`, for a display link
    /// that asks every screen refresh. Cheap when nothing changed: only headers are read.
    public func latest(after revision: Int) -> (image: CGImage, revision: Int)? {
        var best: (slot: Int, revision: Int)?
        for slot in 0..<layout.slots {
            let start = base + layout.headerBytes + slot * layout.slotBytes
            let sequence = start.loadUnaligned(as: UInt64.self)
            let slotRevision = Int(truncatingIfNeeded: start.loadUnaligned(fromByteOffset: 8, as: UInt64.self))
            guard sequence > 0, sequence % 2 == 0, slotRevision > revision else { continue }
            if slotRevision > best?.revision ?? .min { best = (slot, slotRevision) }
        }
        guard let best, let image = image(slot: best.slot) else { return nil }
        return (image, best.revision)
    }

    /// Copies one complete frame, or returns nil if the slot is being written.
    public func image(slot: Int) -> CGImage? {
        guard slot >= 0, slot < layout.slots else { return nil }
        let start = base + layout.headerBytes + slot * layout.slotBytes
        let before = start.loadUnaligned(as: UInt64.self)
        guard before % 2 == 0, before > 0 else { return nil }
        let width = Int(start.loadUnaligned(fromByteOffset: 16, as: UInt32.self))
        let height = Int(start.loadUnaligned(fromByteOffset: 20, as: UInt32.self))
        let bytesPerRow = Int(start.loadUnaligned(fromByteOffset: 24, as: UInt32.self))
        guard width > 0, height > 0, width <= layout.maxWidth, height <= layout.maxHeight,
              bytesPerRow == width * 4 else { return nil }
        let pixels = Data(bytes: start + layout.slotHeaderBytes, count: bytesPerRow * height)
        atomicMemoryFence(ordering: .acquiring)
        guard start.loadUnaligned(as: UInt64.self) == before,
              let provider = CGDataProvider(data: pixels as CFData) else { return nil }
        // BGRA in memory is 32-bit little-endian with the (unused) alpha first.
        let info = CGBitmapInfo(rawValue: CGBitmapInfo.byteOrder32Little.rawValue
                                | CGImageAlphaInfo.noneSkipFirst.rawValue)
        return CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                       bytesPerRow: bytesPerRow, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                       bitmapInfo: info, provider: provider, decode: nil, shouldInterpolate: true,
                       intent: .defaultIntent)
    }
}
