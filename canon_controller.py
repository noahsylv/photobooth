"""
Canon EDSDK tethered-capture backend.

Prerequisites
-------------
1. Install **Canon EOS Utility** (or obtain the EDSDK developer package from
   https://developercommunity.usa.canon.com/canon) so that EDSDK.dll is
   available on the host PC.
2. Connect the Canon EOS R50 (or compatible body) via USB-C and power it on.
3. Make sure Canon EOS Utility is *closed* – only one application may hold the
   camera session at a time.
4. Set the camera to a still-photo shooting mode (P / Av / Tv / M / Auto).
   The flash fires automatically based on the camera's own metering.

How it works
------------
* connect()         – loads EDSDK.dll, enumerates cameras, opens a session,
                      and configures the camera to save images to the PC.
* start_live_view() – enables the camera's Electronic Viewfinder (EVF) output
                      to the PC and spawns a background thread that continuously
                      pulls JPEG frames for the preview window.
* capture_photo()   – sends a TakePicture command, waits for the SDK's
                      DirItemCreated callback, downloads the JPEG, and returns
                      the saved path.
* disconnect()      – stops live view, closes the session, and terminates the SDK.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time
import winreg
from pathlib import Path

import cv2
import numpy as np
import win32gui

from camera_controller import CameraController

# ── EDSDK numeric constants ───────────────────────────────────────────────────

EDS_ERR_OK = 0x00000000

# Property IDs  (verified against EDSDKTypes.h from EDSDK v13.20.21)
kEdsPropID_SaveTo              = 0x0000000b
kEdsPropID_Evf_OutputDevice    = 0x00000500

# SaveTo destination
kEdsSaveTo_Host = 2

# EVF output device flags
kEdsEvfOutputDevice_PC = 0x00000002

# Camera commands  (verified against EDSDKTypes.h)
kEdsCameraCommand_PressShutterButton              = 0x00000004
kEdsCameraCommand_ShutterButton_OFF               = 0x00000000
kEdsCameraCommand_ShutterButton_Completely_NonAF  = 0x00010003

# Object events
kEdsObjectEvent_All                      = 0x00000200
kEdsObjectEvent_DirItemCreated           = 0x00000203
kEdsObjectEvent_DirItemRequestTransfer   = 0x00000207
kEdsObjectEvent_DirItemRequestTransferDT = 0x00000208

# File create disposition / access
kEdsFileCreateDisposition_CreateAlways = 1
kEdsAccess_ReadWrite                   = 2

EDS_MAX_NAME = 256
EDS_ERR_DEVICE_BUSY = 0x00000081

_CAPTURE_TIMEOUT_S = 30.0   # seconds to wait for the image-ready event


# ── ctypes structs ────────────────────────────────────────────────────────────

class _EdsDirectoryItemInfo(ctypes.Structure):
    _fields_ = [
        ("size",       ctypes.c_uint64),
        ("isFolder",   ctypes.c_int32),
        ("groupID",    ctypes.c_uint32),
        ("option",     ctypes.c_uint32),
        ("szFileName", ctypes.c_char * EDS_MAX_NAME),
        ("format",     ctypes.c_uint32),
        ("dateTime",   ctypes.c_uint32),
    ]


class _EdsCapacity(ctypes.Structure):
    """Passed by value to EdsSetCapacity."""
    _fields_ = [
        ("numberOfFreeClusters", ctypes.c_int32),
        ("bytesPerSector",       ctypes.c_int32),
        ("reset",                ctypes.c_int32),   # EdsBool
    ]


# Callback prototype (stdcall / WINAPI convention)
_OBJECT_EVENT_HANDLER = ctypes.WINFUNCTYPE(
    ctypes.c_uint32,   # EdsError  (return)
    ctypes.c_uint32,   # EdsObjectEvent inEvent
    ctypes.c_void_p,   # EdsBaseRef     inRef
    ctypes.c_void_p,   # EdsVoid*       inContext
)


# ── DLL discovery ─────────────────────────────────────────────────────────────

def _find_edsdk_dll() -> Path:
    """
    Return the path to EDSDK.dll by searching:
      1. The directory containing this script (allows manual bundling).
      2. Common Canon EOS Utility / Digital Photo Professional install paths.
      3. The Windows registry.
    Raises FileNotFoundError with a helpful message if the DLL cannot be found.
    """
    # 1. Bundled alongside the script
    local = Path(__file__).parent / "EDSDK.dll"
    if local.exists():
        return local

    # 2. Common installation paths (both 64-bit and 32-bit Program Files)
    candidates = [
        r"C:\Program Files\Canon\EOS Utility 3\EDSDK.dll",
        r"C:\Program Files (x86)\Canon\EOS Utility 3\EDSDK.dll",
        r"C:\Program Files\Canon\EOS Digital Solution\EDSDK.dll",
        r"C:\Program Files (x86)\Canon\EOS Digital Solution\EDSDK.dll",
        r"C:\Program Files\Canon\EOS Utility\EDSDK.dll",
        r"C:\Program Files (x86)\Canon\EOS Utility\EDSDK.dll",
        r"C:\Program Files\Canon\EOS Utility\EU3\EDSDK.dll",
        r"C:\Program Files (x86)\Canon\EOS Utility\EU3\EDSDK.dll",
        r"C:\Program Files\Canon\Digital Photo Professional 4\EDSDK.dll",
        r"C:\Program Files (x86)\Canon\Digital Photo Professional 4\EDSDK.dll",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            return p

    # 3. Registry (EDSDK installer sometimes writes an InstallPath key)
    reg_keys = [
        r"SOFTWARE\Canon\EOS Digital Solution\EDSDKVersion",
        r"SOFTWARE\WOW6432Node\Canon\EOS Digital Solution\EDSDKVersion",
    ]
    for key_path in reg_keys:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            dll = Path(install_path) / "EDSDK.dll"
            if dll.exists():
                return dll
        except OSError:
            pass

    raise FileNotFoundError(
        "EDSDK.dll not found.\n"
        "Install Canon EOS Utility from https://www.usa.canon.com/support  OR\n"
        "download the EDSDK developer package and place EDSDK.dll in the same\n"
        "directory as this script.  Alternatively set config.EDSDK_DLL_PATH."
    )


# ── CanonController ───────────────────────────────────────────────────────────

class CanonController(CameraController):
    """
    CameraController implementation backed by the Canon EOS SDK (EDSDK).

    Supports live-view preview via the camera's Electronic Viewfinder and
    full-resolution JPEG capture with the camera's built-in flash.
    """

    def __init__(self, dll_path: str | None = None) -> None:
        self._dll_path = Path(dll_path) if dll_path else _find_edsdk_dll()
        self._sdk: ctypes.WinDLL | None = None
        self._camera_ref: ctypes.c_void_p | None = None

        # Live-view state
        self._lv_thread: threading.Thread | None = None
        self._lv_stop = threading.Event()
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()

        # Capture synchronisation
        self._capture_event = threading.Event()
        self._pending_output_path: Path | None = None
        self._pending_dir_item_ref: ctypes.c_void_p | None = None
        self._capture_error: str | None = None

        # Keep the callback object alive so the GC does not collect it
        self._obj_event_cb = _OBJECT_EVENT_HANDLER(self._on_object_event)

    # ── public CameraController interface ────────────────────────────────────

    def connect(self) -> None:
        """Initialize EDSDK, detect the first connected Canon camera, open a session."""
        sdk = ctypes.WinDLL(str(self._dll_path))
        self._setup_prototypes(sdk)

        err = sdk.EdsInitializeSDK()
        if err != EDS_ERR_OK:
            raise RuntimeError(f"EdsInitializeSDK failed: 0x{err:08X}")

        camera_list = ctypes.c_void_p()
        err = sdk.EdsGetCameraList(ctypes.byref(camera_list))
        if err != EDS_ERR_OK:
            sdk.EdsTerminateSDK()
            raise RuntimeError(f"EdsGetCameraList failed: 0x{err:08X}")

        count = ctypes.c_uint32(0)
        sdk.EdsGetChildCount(camera_list, ctypes.byref(count))
        if count.value == 0:
            sdk.EdsRelease(camera_list)
            sdk.EdsTerminateSDK()
            raise RuntimeError(
                "No Canon camera detected.\n"
                "  • Ensure the camera is connected via USB and powered on.\n"
                "  • Close Canon EOS Utility if it is running.\n"
                "  • Try a different USB port or cable."
            )

        camera_ref = ctypes.c_void_p()
        err = sdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera_ref))
        sdk.EdsRelease(camera_list)
        if err != EDS_ERR_OK:
            sdk.EdsTerminateSDK()
            raise RuntimeError(f"EdsGetChildAtIndex failed: 0x{err:08X}")

        err = sdk.EdsOpenSession(camera_ref)
        if err != EDS_ERR_OK:
            sdk.EdsRelease(camera_ref)
            sdk.EdsTerminateSDK()
            raise RuntimeError(
                f"EdsOpenSession failed: 0x{err:08X}\n"
                "Close Canon EOS Utility — only one application may hold the "
                "camera session at a time."
            )

        # Direct the camera to deliver captured images to the PC (not the card)
        save_to = ctypes.c_uint32(kEdsSaveTo_Host)
        sdk.EdsSetPropertyData(
            camera_ref,
            kEdsPropID_SaveTo,
            0,
            ctypes.sizeof(save_to),
            ctypes.byref(save_to),
        )

        # Tell the camera how much free space is on the host PC.
        # Required when SaveTo=Host; without this the camera ignores the
        # save-to-host setting and sends no DirItemCreated event.
        cap = _EdsCapacity()
        cap.numberOfFreeClusters = 0x7FFFFFFF
        cap.bytesPerSector       = 512
        cap.reset                = 1
        sdk.EdsSetCapacity(camera_ref, cap)

        # Register the object-event handler that fires when an image is ready
        sdk.EdsSetObjectEventHandler(
            camera_ref,
            kEdsObjectEvent_All,
            self._obj_event_cb,
            None,
        )

        self._sdk = sdk
        self._camera_ref = camera_ref

    def start_live_view(self) -> None:
        """Enable the camera's Electronic Viewfinder output to the PC."""
        if self._lv_thread is not None and self._lv_thread.is_alive():
            return

        device = ctypes.c_uint32(kEdsEvfOutputDevice_PC)
        self._sdk.EdsSetPropertyData(
            self._camera_ref,
            kEdsPropID_Evf_OutputDevice,
            0,
            ctypes.sizeof(device),
            ctypes.byref(device),
        )

        self._lv_stop.clear()
        self._lv_thread = threading.Thread(
            target=self._live_view_worker,
            name="CanonLiveView",
            daemon=True,
        )
        self._lv_thread.start()

    def stop_live_view(self) -> None:
        """Stop pulling EVF frames and turn off the camera's PC output."""
        self._lv_stop.set()
        if self._lv_thread is not None:
            self._lv_thread.join(timeout=3.0)
            self._lv_thread = None

        if self._sdk is not None and self._camera_ref is not None:
            device = ctypes.c_uint32(0)
            self._sdk.EdsSetPropertyData(
                self._camera_ref,
                kEdsPropID_Evf_OutputDevice,
                0,
                ctypes.sizeof(device),
                ctypes.byref(device),
            )

    def read_frame(self) -> np.ndarray:
        """Return the latest EVF preview frame as a BGR numpy array."""
        with self._frame_lock:
            if self._latest_frame is None:
                raise RuntimeError(
                    "No live-view frame available yet. "
                    "Ensure start_live_view() was called."
                )
            return self._latest_frame.copy()

    def capture_photo(self, output_path: Path) -> Path:
        """
        Fire the shutter via EDSDK, wait for the image-ready event, download
        the JPEG to *output_path*, and return *output_path*.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Stop the live-view thread before capturing.  EDSDK is not
        # thread-safe: a concurrent EdsDownloadEvfImage call on the live-view
        # thread will deadlock the SDK's internal lock the moment TakePicture
        # is sent from the main thread, freezing the process.
        lv_was_running = (
            self._lv_thread is not None and self._lv_thread.is_alive()
        )
        if lv_was_running:
            self._lv_stop.set()
            # Pump messages while waiting for the LV thread to exit.
            # EdsDownloadEvfImage (called by the LV thread) may need the main
            # thread's Win32 message pump to complete — a plain join() here
            # would deadlock on subsequent captures.
            deadline = time.monotonic() + 3.0
            while self._lv_thread.is_alive() and time.monotonic() < deadline:
                win32gui.PumpWaitingMessages()
                cv2.waitKey(1)
                time.sleep(0.01)
            self._lv_thread = None

        self._pending_output_path = output_path
        self._capture_error = None
        self._capture_event.clear()

        err = EDS_ERR_OK
        for _ in range(10):
            err = self._sdk.EdsSendCommand(
                self._camera_ref,
                kEdsCameraCommand_PressShutterButton,
                kEdsCameraCommand_ShutterButton_Completely_NonAF,
            )
            if err != EDS_ERR_DEVICE_BUSY:
                break
            time.sleep(0.2)
        # Always release the simulated button press
        self._sdk.EdsSendCommand(
            self._camera_ref,
            kEdsCameraCommand_PressShutterButton,
            kEdsCameraCommand_ShutterButton_OFF,
        )
        if err != EDS_ERR_OK:
            raise RuntimeError(
                f"PressShutterButton failed: 0x{err:08X}\n"
                "Ensure the camera is in a still-photo shooting mode "
                "(not Movie / Video mode)."
            )

        # Pump Windows messages until the DirItemCreated callback fires.
        # The callback intentionally does NOT call EdsDownload — doing so
        # inside PumpWaitingMessages blocks the message dispatch and freezes
        # the window.  The download happens below, after the pump returns.
        deadline = time.monotonic() + _CAPTURE_TIMEOUT_S
        while not self._capture_event.is_set():
            win32gui.PumpWaitingMessages()
            cv2.waitKey(1)  # keeps the OpenCV window from going "(Not Responding)"
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Timed out after {_CAPTURE_TIMEOUT_S}s waiting for the "
                    "camera to deliver the captured image."
                )
            time.sleep(0.01)

        # Download from the main thread now that the pump loop has exited.
        if self._pending_dir_item_ref is not None:
            try:
                self._download_dir_item(self._pending_dir_item_ref, output_path)
            except Exception as exc:
                self._capture_error = str(exc)
            finally:
                self._sdk.EdsRelease(self._pending_dir_item_ref)
                self._pending_dir_item_ref = None

        if self._capture_error:
            raise RuntimeError(f"Image download failed: {self._capture_error}")

        # Restart live view for the preview window between shots
        if lv_was_running:
            self._lv_stop.clear()
            self._lv_thread = threading.Thread(
                target=self._live_view_worker,
                name="CanonLiveView",
                daemon=True,
            )
            self._lv_thread.start()

        return output_path

    def disconnect(self) -> None:
        """Stop live view, close the camera session, and terminate the SDK."""
        if self._sdk is None:
            return
        try:
            self.stop_live_view()
        except Exception:
            pass
        if self._camera_ref is not None:
            self._sdk.EdsCloseSession(self._camera_ref)
            self._sdk.EdsRelease(self._camera_ref)
            self._camera_ref = None
        self._sdk.EdsTerminateSDK()
        self._sdk = None

    # ── private helpers ───────────────────────────────────────────────────────

    def _on_object_event(
        self,
        event: int,
        obj_ref: int,          # received as a plain Python int from ctypes
        context: int,
    ) -> int:
        """
        EDSDK object-event callback — invoked on the SDK's internal thread.

        When the camera signals DirItemCreated (new image on PC), download the
        file and set the capture event so capture_photo() can return.
        """
        if event in (kEdsObjectEvent_DirItemCreated,
                    kEdsObjectEvent_DirItemRequestTransfer,
                    kEdsObjectEvent_DirItemRequestTransferDT) and obj_ref and self._pending_output_path is not None:
            # Store the ref — the download is performed by capture_photo() after
            # PumpWaitingMessages() returns.  Calling EdsDownload() here (inside
            # the Windows message dispatch) would block the pump and freeze the UI.
            self._pending_dir_item_ref = ctypes.c_void_p(obj_ref)
            self._capture_event.set()
            # Do NOT release obj_ref — capture_photo() releases it after download.
        elif obj_ref:
            self._sdk.EdsRelease(ctypes.c_void_p(obj_ref))
        return EDS_ERR_OK

    def _download_dir_item(
        self, dir_item_ref: ctypes.c_void_p, output_path: Path
    ) -> None:
        """Download a camera directory item (image file) to *output_path*."""
        info = _EdsDirectoryItemInfo()
        err = self._sdk.EdsGetDirectoryItemInfo(dir_item_ref, ctypes.byref(info))
        if err != EDS_ERR_OK:
            raise RuntimeError(f"EdsGetDirectoryItemInfo failed: 0x{err:08X}")

        stream = ctypes.c_void_p()
        err = self._sdk.EdsCreateFileStream(
            str(output_path).encode("mbcs"),
            kEdsFileCreateDisposition_CreateAlways,
            kEdsAccess_ReadWrite,
            ctypes.byref(stream),
        )
        if err != EDS_ERR_OK:
            raise RuntimeError(f"EdsCreateFileStream failed: 0x{err:08X}")

        try:
            err = self._sdk.EdsDownload(dir_item_ref, info.size, stream)
            if err != EDS_ERR_OK:
                raise RuntimeError(f"EdsDownload failed: 0x{err:08X}")
            self._sdk.EdsDownloadComplete(dir_item_ref)
        finally:
            self._sdk.EdsRelease(stream)

    def _live_view_worker(self) -> None:
        """Background thread: continuously pulls EVF JPEG frames (~30 fps)."""
        while not self._lv_stop.is_set():
            try:
                frame = self._pull_evf_frame()
                if frame is not None:
                    with self._frame_lock:
                        self._latest_frame = frame
            except Exception:
                pass
            time.sleep(0.033)

    def _pull_evf_frame(self) -> np.ndarray | None:
        """Download one EVF JPEG from the camera and decode it to a BGR array."""
        stream = ctypes.c_void_p()
        err = self._sdk.EdsCreateMemoryStream(ctypes.c_uint64(0), ctypes.byref(stream))
        if err != EDS_ERR_OK:
            return None

        evf_image = ctypes.c_void_p()
        err = self._sdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            self._sdk.EdsRelease(stream)
            return None

        err = self._sdk.EdsDownloadEvfImage(self._camera_ref, evf_image)
        self._sdk.EdsRelease(evf_image)
        if err != EDS_ERR_OK:
            self._sdk.EdsRelease(stream)
            return None

        length = ctypes.c_uint64(0)
        err = self._sdk.EdsGetLength(stream, ctypes.byref(length))
        if err != EDS_ERR_OK or length.value == 0:
            self._sdk.EdsRelease(stream)
            return None

        ptr = ctypes.c_void_p()
        err = self._sdk.EdsGetPointer(stream, ctypes.byref(ptr))
        if err != EDS_ERR_OK or ptr.value is None:
            self._sdk.EdsRelease(stream)
            return None

        # Copy the JPEG bytes before releasing the stream
        buf = (ctypes.c_uint8 * length.value).from_address(ptr.value)
        data = np.frombuffer(buf, dtype=np.uint8).copy()
        self._sdk.EdsRelease(stream)

        return cv2.imdecode(data, cv2.IMREAD_COLOR)

    def _setup_prototypes(self, sdk: ctypes.WinDLL) -> None:
        """
        Declare argtypes / restype for every EDSDK function we call so ctypes
        marshals arguments correctly on 64-bit Windows.
        """
        vp    = ctypes.c_void_p
        u32   = ctypes.c_uint32
        u64   = ctypes.c_uint64
        i32   = ctypes.c_int32
        pvp   = ctypes.POINTER(ctypes.c_void_p)
        pu32  = ctypes.POINTER(ctypes.c_uint32)
        pu64  = ctypes.POINTER(ctypes.c_uint64)

        sdk.EdsInitializeSDK.restype  = u32
        sdk.EdsInitializeSDK.argtypes = []

        sdk.EdsTerminateSDK.restype  = u32
        sdk.EdsTerminateSDK.argtypes = []

        sdk.EdsGetCameraList.restype  = u32
        sdk.EdsGetCameraList.argtypes = [pvp]

        sdk.EdsGetChildCount.restype  = u32
        sdk.EdsGetChildCount.argtypes = [vp, pu32]

        sdk.EdsGetChildAtIndex.restype  = u32
        sdk.EdsGetChildAtIndex.argtypes = [vp, i32, pvp]

        sdk.EdsOpenSession.restype  = u32
        sdk.EdsOpenSession.argtypes = [vp]

        sdk.EdsCloseSession.restype  = u32
        sdk.EdsCloseSession.argtypes = [vp]

        sdk.EdsRelease.restype  = u32
        sdk.EdsRelease.argtypes = [vp]

        sdk.EdsSetPropertyData.restype  = u32
        sdk.EdsSetPropertyData.argtypes = [vp, u32, i32, u32, vp]

        sdk.EdsSetObjectEventHandler.restype  = u32
        sdk.EdsSetObjectEventHandler.argtypes = [vp, u32, vp, vp]

        sdk.EdsSendCommand.restype  = u32
        sdk.EdsSendCommand.argtypes = [vp, u32, i32]

        sdk.EdsGetDirectoryItemInfo.restype  = u32
        sdk.EdsGetDirectoryItemInfo.argtypes = [vp, ctypes.POINTER(_EdsDirectoryItemInfo)]

        sdk.EdsCreateFileStream.restype  = u32
        sdk.EdsCreateFileStream.argtypes = [ctypes.c_char_p, u32, u32, pvp]

        sdk.EdsDownload.restype  = u32
        sdk.EdsDownload.argtypes = [vp, u64, vp]

        sdk.EdsDownloadComplete.restype  = u32
        sdk.EdsDownloadComplete.argtypes = [vp]

        sdk.EdsCreateMemoryStream.restype  = u32
        sdk.EdsCreateMemoryStream.argtypes = [u64, pvp]

        sdk.EdsCreateEvfImageRef.restype  = u32
        sdk.EdsCreateEvfImageRef.argtypes = [vp, pvp]

        sdk.EdsDownloadEvfImage.restype  = u32
        sdk.EdsDownloadEvfImage.argtypes = [vp, vp]

        sdk.EdsGetLength.restype  = u32
        sdk.EdsGetLength.argtypes = [vp, pu64]

        sdk.EdsGetPointer.restype  = u32
        sdk.EdsGetPointer.argtypes = [vp, pvp]

        sdk.EdsSetCapacity.restype  = u32
        sdk.EdsSetCapacity.argtypes = [vp, _EdsCapacity]  # struct passed by value
