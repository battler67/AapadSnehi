/** Read a JPEG EXIF GPS suggestion only. Malformed/absent metadata is ignored.
 * The original photo stays on the device; compression removes EXIF before upload.
 */
export function photoLocation(buffer: ArrayBuffer): [number, number] | null {
  try {
    const view = new DataView(buffer);
    if (view.getUint16(0) !== 0xffd8) return null;
    let position = 2;
    while (position + 4 < view.byteLength) {
      const marker = view.getUint16(position);
      if (marker === 0xffda || marker === 0xffd9) return null;
      const length = view.getUint16(position + 2);
      if (length < 2 || position + 2 + length > view.byteLength) return null;
      if (marker === 0xffe1 && view.getUint32(position + 4) === 0x45786966) {
        const base = position + 10;
        const little = view.getUint16(base) === 0x4949;
        if (!little && view.getUint16(base) !== 0x4d4d) return null;
        const u16 = (at: number) => view.getUint16(base + at, little);
        const u32 = (at: number) => view.getUint32(base + at, little);
        if (u16(2) !== 42) return null;
        const directory = u32(4);
        let gps = 0;
        for (let i = 0; i < Math.min(u16(directory), 256); i++) {
          const at = directory + 2 + i * 12;
          if (u16(at) === 0x8825) gps = u32(at + 8);
        }
        if (!gps) return null;
        let lat: number | null = null, lon: number | null = null;
        let latRef = "", lonRef = "";
        for (let i = 0; i < Math.min(u16(gps), 64); i++) {
          const at = gps + 2 + i * 12, tag = u16(at);
          if (tag === 1 || tag === 3) {
            const ref = String.fromCharCode(view.getUint8(base + at + 8));
            if (tag === 1) latRef = ref; else lonRef = ref;
          }
          if ((tag === 2 || tag === 4) && u16(at + 2) === 5 && u32(at + 4) === 3) {
            const offset = u32(at + 8);
            const values = [0, 8, 16].map(delta => u32(offset + delta) / u32(offset + delta + 4));
            const coordinate = values[0] + values[1] / 60 + values[2] / 3600;
            if (tag === 2) lat = coordinate; else lon = coordinate;
          }
        }
        if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon) || lat > 90 || lon > 180 || !["N", "S"].includes(latRef) || !["E", "W"].includes(lonRef)) return null;
        return [lat * (latRef === "S" ? -1 : 1), lon * (lonRef === "W" ? -1 : 1)];
      }
      position += length + 2;
    }
  } catch { /* Malformed EXIF is not location evidence. */ }
  return null;
}
