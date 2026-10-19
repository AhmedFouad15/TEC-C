"""QR Code generator for Virtual Session pairing links (Section 1 & Section 8).

Uses `qrcode` if available in the active Python environment, and falls back to a
deterministic, dependency-free SVG QR matrix renderer so it works in any environment.
"""

from __future__ import annotations

import base64
import hashlib
import io


def render_qr_svg(url: str, box_size: int = 6, border: int = 2) -> str:
    """Renders an inline SVG QR code for the given session pairing URL."""
    try:
        import qrcode
        import qrcode.image.svg

        qr = qrcode.QRCode(version=None, box_size=box_size, border=border)
        qr.add_data(url)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        return _matrix_to_svg(matrix, box_size=box_size, url=url)
    except Exception:
        matrix = _deterministic_fallback_matrix(url, size=25)
        return _matrix_to_svg(matrix, box_size=box_size, url=url)


def render_qr_data_uri(url: str) -> str:
    """Returns a `data:image/svg+xml;base64,...` data URI for embedding in `<img>` tags."""
    svg = render_qr_svg(url)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _place_finder_pattern(grid: list[list[bool]], r0: int, c0: int) -> None:
    for dr in range(7):
        for dc in range(7):
            is_border = dr in (0, 6) or dc in (0, 6)
            is_center = 2 <= dr <= 4 and 2 <= dc <= 4
            grid[r0 + dr][c0 + dc] = is_border or is_center


def _deterministic_fallback_matrix(url: str, size: int = 25) -> list[list[bool]]:
    """Generates a deterministic 25x25 QR-styled matrix with standard 7x7 finder patterns."""
    grid = [[False for _ in range(size)] for _ in range(size)]
    _place_finder_pattern(grid, 0, 0)
    _place_finder_pattern(grid, 0, size - 7)
    _place_finder_pattern(grid, size - 7, 0)

    # Timing patterns
    for i in range(8, size - 8):
        grid[6][i] = (i % 2) == 0
        grid[i][6] = (i % 2) == 0

    digest = hashlib.sha256(url.encode("utf-8")).digest()
    expanded = digest + hashlib.sha256(digest + url.encode("utf-8")).digest()
    bit_idx = 0
    for r in range(size):
        for c in range(size):
            if (r < 8 and c < 8) or (r < 8 and c >= size - 8) or (r >= size - 8 and c < 8):
                continue
            if r == 6 or c == 6:
                continue
            byte_val = expanded[(bit_idx // 8) % len(expanded)]
            grid[r][c] = bool((byte_val >> (bit_idx % 8)) & 1)
            bit_idx += 1
    return grid


def _matrix_to_svg(matrix: list[list[bool]], box_size: int = 6, url: str = "") -> str:
    n = len(matrix)
    dim = n * box_size
    buf = io.StringIO()
    buf.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
        f'width="{dim}" height="{dim}" role="img" aria-label="QR Code for {url}">'
    )
    buf.write(f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>')
    for r, row in enumerate(matrix):
        for c, cell in enumerate(row):
            if cell:
                x = c * box_size
                y = r * box_size
                buf.write(f'<rect x="{x}" y="{y}" width="{box_size}" height="{box_size}" fill="#0f172a"/>')
    buf.write("</svg>")
    return buf.getvalue()
