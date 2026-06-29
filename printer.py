from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageWin

try:
    import win32con
    import win32print
    import win32ui
except ImportError as exc:  # pragma: no cover - environment specific
    raise RuntimeError("pywin32 is required for printing. Install pywin32 first.") from exc


def _prepare_image(
    image: Image.Image,
    target_w: int,
    target_h: int,
    rotation_degrees: int = 0,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Rotate the image then resize to exactly fill the printer DC.

    The generated strip is sized so that after rotation its dimensions equal the
    printer DC (1844×1240), giving a 1:1 draw with no letterboxing.
    """
    img = image
    if rotation_degrees:
        img = img.rotate(rotation_degrees, expand=True)

    if img.width != target_w or img.height != target_h:
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    return img, (0, 0, target_w, target_h)


def print_image(
    image_path: str,
    printer_name: str = "DS-RX1",
    rotation_degrees: int = 0,
) -> None:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    hprinter = win32print.OpenPrinter(printer_name)
    try:
        printer_info = win32print.GetPrinter(hprinter, 2)
    finally:
        win32print.ClosePrinter(hprinter)

    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_info["pPrinterName"])

    try:
        printable_w = hdc.GetDeviceCaps(win32con.HORZRES)
        printable_h = hdc.GetDeviceCaps(win32con.VERTRES)
        phys_w = hdc.GetDeviceCaps(win32con.PHYSICALWIDTH)
        phys_h = hdc.GetDeviceCaps(win32con.PHYSICALHEIGHT)
        dpi_x = hdc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y = hdc.GetDeviceCaps(win32con.LOGPIXELSY)
        print(f"[printer] printable area : {printable_w} x {printable_h} px")
        print(f"[printer] physical paper : {phys_w} x {phys_h} px")
        print(f"[printer] DPI            : {dpi_x} x {dpi_y}")

        with Image.open(path) as img:
            image = img.convert("RGB")
            print(f"[printer] source image   : {image.width} x {image.height} px")
            prepared, draw_rect = _prepare_image(
                image,
                printable_w,
                printable_h,
                rotation_degrees=rotation_degrees,
            )
            print(f"[printer] prepared image : {prepared.width} x {prepared.height} px  rect={draw_rect}")

            # Save a preview PNG alongside the print file so you can inspect it.
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            preview_path = path.parent / f"preview_{ts}.png"
            prepared.save(str(preview_path))
            print(f"[printer] preview saved  : {preview_path}")

            dib = ImageWin.Dib(prepared)

            hdc.StartDoc(path.name)
            hdc.StartPage()
            dib.draw(hdc.GetHandleOutput(), draw_rect)
            hdc.EndPage()
            hdc.EndDoc()
    finally:
        hdc.DeleteDC()
