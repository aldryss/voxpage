"""Trame d'en-tête « Info » (Xing/LAME) d'un MP3 CBR : nombre de trames, délai et remplissage.

lameenc ne l'écrit pas ; sans elle, les lecteurs ne connaissent ni la durée exacte ni le délai de
l'encodeur (~50 ms de blanc au début, jusqu'à une trame de plus à la fin). On réserve la trame au
début du fichier et on la complète à la fermeture.
"""

import struct

ENCODER_DELAY = 576  # délai de l'encodeur LAME, en échantillons

_BITRATES_V1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
_BITRATES_V2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def parse_header(h: bytes) -> tuple[int, int] | None:
    """(longueur de la trame, échantillons par trame) pour un en-tête MPEG couche III, sinon None."""
    if len(h) < 4 or h[0] != 0xFF or (h[1] & 0xE0) != 0xE0:
        return None
    version = (h[1] >> 3) & 3
    if version == 1 or (h[1] >> 1) & 3 != 1:
        return None
    bitrate_idx, rate_idx = h[2] >> 4, (h[2] >> 2) & 3
    if bitrate_idx in (0, 15) or rate_idx == 3:
        return None
    padding = (h[2] >> 1) & 1
    rate = _RATES[version][rate_idx]
    if version == 3:
        return 144 * _BITRATES_V1[bitrate_idx] * 1000 // rate + padding, 1152
    return 72 * _BITRATES_V2[bitrate_idx] * 1000 // rate + padding, 576


class FrameCounter:
    """Compte les trames MP3 d'un flux reçu par morceaux (trames éventuellement coupées)."""

    def __init__(self) -> None:
        self.frames = 0
        self.ok = True
        self._carry = b""

    def feed(self, data: bytes) -> None:
        if not self.ok:
            return
        buf = self._carry + data
        pos = 0
        while pos + 4 <= len(buf):
            info = parse_header(buf[pos : pos + 4])
            if info is None:
                self.ok = False  # flux inattendu : on renonce à l'en-tête Info
                return
            if pos + info[0] > len(buf):
                break
            pos += info[0]
            self.frames += 1
        self._carry = buf[pos:]


def info_frame(header: bytes, frames: int, total_bytes: int, samples: int, bitrate_kbps: int) -> bytes:
    """Trame Info complète. `header` : en-tête (4 octets) du flux, `frames` : trames audio (hors Info)."""
    h = bytearray(header[:4])
    h[2] &= ~0x02  # pas de bit de remplissage : longueur fixe
    parsed = parse_header(bytes(h))
    assert parsed is not None
    length, spf = parsed
    mpeg1 = ((h[1] >> 3) & 3) == 3
    channels_mono = (h[3] >> 6) == 3
    side_info = (17 if mpeg1 else 9) if channels_mono else (32 if mpeg1 else 17)
    padding = max(0, min(4095, frames * spf - ENCODER_DELAY - samples))
    body = bytearray()
    body += b"Info" + struct.pack(">III", 3, frames, total_bytes)  # drapeaux : trames + octets
    body += b"LAME3.100"
    body += bytes([0x01, 0])  # révision 0 / méthode CBR ; filtre passe-bas inconnu
    body += bytes(4 + 2 + 2)  # pic, gains
    body += bytes([0, min(bitrate_kbps, 255)])  # drapeaux d'encodage, débit
    delay_padding = (ENCODER_DELAY << 12) | padding
    body += delay_padding.to_bytes(3, "big")
    body += bytes([0, 0, 0, 0])  # mode, gain MP3, préréglage
    body += struct.pack(">IHH", total_bytes, 0, 0)  # longueur musique, CRC (non calculés)
    frame = bytes(h) + bytes(side_info) + bytes(body)
    return frame + bytes(length - len(frame))
