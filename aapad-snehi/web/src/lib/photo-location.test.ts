import { describe, expect, it } from "vitest";
import { photoLocation } from "./photo-location";

describe("untrusted photo location metadata", () => {
  it("does not manufacture a point from missing or malformed metadata", () => {
    expect(photoLocation(new ArrayBuffer(0))).toBeNull();
    expect(photoLocation(new Uint8Array([255, 216, 255, 225, 255, 255]).buffer)).toBeNull();
  });
  it("reads a JPEG GPS suggestion without inferring accuracy or confirmation", () => {
    const buffer = new ArrayBuffer(150), view = new DataView(buffer);
    view.setUint16(0, 0xffd8); view.setUint16(2, 0xffe1); view.setUint16(4, 146); view.setUint32(6, 0x45786966);
    const base = 12;
    view.setUint16(base, 0x4949); view.setUint16(base+2, 42, true); view.setUint32(base+4, 8, true);
    view.setUint16(base+8, 1, true); view.setUint16(base+10, 0x8825, true); view.setUint32(base+18, 26, true);
    view.setUint16(base+26, 4, true);
    for (let i=0; i<4; i++) { const at=base+28+i*12; view.setUint16(at, i+1, true); view.setUint16(at+2, i%2 ? 5 : 2, true); view.setUint32(at+4, i%2 ? 3 : 2, true); }
    view.setUint8(base+36, 78); view.setUint8(base+60, 69);
    view.setUint32(base+48, 80, true); view.setUint32(base+72, 104, true);
    for (const [offset, degrees] of [[80, 17], [104, 78]]) { view.setUint32(base+offset, degrees, true); view.setUint32(base+offset+4, 1, true); view.setUint32(base+offset+8, 30, true); view.setUint32(base+offset+12, 1, true); view.setUint32(base+offset+20, 1, true); }
    expect(photoLocation(buffer)).toEqual([17.5, 78.5]);
  });
});
