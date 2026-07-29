"""
Minimal Canon EDSDK test script.

Run with:  py test_canon.py
Press Enter when prompted to fire the shutter.
The captured JPEG will be saved to  test_capture.jpg  in this directory.
"""

import ctypes
import ctypes.wintypes
import time
import struct
from pathlib import Path

import win32gui

# ── Load DLL ─────────────────────────────────────────────────────────────────

DLL_PATH = Path(__file__).parent / "EDSDK.dll"
assert DLL_PATH.exists(), f"EDSDK.dll not found at {DLL_PATH}"

# Verify it is 64-bit
with open(DLL_PATH, "rb") as f:
    f.seek(0x3C)
    pe_off = struct.unpack("<I", f.read(4))[0]
    f.seek(pe_off + 4)
    machine = struct.unpack("<H", f.read(2))[0]
arch = {0x014C: "32-bit (WRONG)", 0x8664: "64-bit (OK)"}.get(machine, hex(machine))
print(f"[1] EDSDK.dll architecture: {arch}")
assert machine == 0x8664, "Need the 64-bit EDSDK.dll"

sdk = ctypes.WinDLL(str(DLL_PATH))
print("[2] DLL loaded OK")

# ── Prototypes ────────────────────────────────────────────────────────────────

vp   = ctypes.c_void_p
pvp  = ctypes.POINTER(ctypes.c_void_p)
u32  = ctypes.c_uint32
u64  = ctypes.c_uint64
i32  = ctypes.c_int32
pu32 = ctypes.POINTER(ctypes.c_uint32)
pu64 = ctypes.POINTER(ctypes.c_uint64)

EDS_MAX_NAME = 256

class EdsDirectoryItemInfo(ctypes.Structure):
    _fields_ = [
        ("size",       ctypes.c_uint64),
        ("isFolder",   ctypes.c_int32),
        ("groupID",    ctypes.c_uint32),
        ("option",     ctypes.c_uint32),
        ("szFileName", ctypes.c_char * EDS_MAX_NAME),
        ("format",     ctypes.c_uint32),
        ("dateTime",   ctypes.c_uint32),
    ]

sdk.EdsInitializeSDK.restype  = u32; sdk.EdsInitializeSDK.argtypes  = []
sdk.EdsTerminateSDK.restype   = u32; sdk.EdsTerminateSDK.argtypes   = []
sdk.EdsGetCameraList.restype  = u32; sdk.EdsGetCameraList.argtypes  = [pvp]
sdk.EdsGetChildCount.restype  = u32; sdk.EdsGetChildCount.argtypes  = [vp, pu32]
sdk.EdsGetChildAtIndex.restype = u32; sdk.EdsGetChildAtIndex.argtypes = [vp, i32, pvp]
sdk.EdsOpenSession.restype    = u32; sdk.EdsOpenSession.argtypes    = [vp]
sdk.EdsCloseSession.restype   = u32; sdk.EdsCloseSession.argtypes   = [vp]
sdk.EdsRelease.restype        = u32; sdk.EdsRelease.argtypes        = [vp]
sdk.EdsSetPropertyData.restype = u32; sdk.EdsSetPropertyData.argtypes = [vp, u32, i32, u32, vp]
sdk.EdsSetObjectEventHandler.restype = u32; sdk.EdsSetObjectEventHandler.argtypes = [vp, u32, vp, vp]
sdk.EdsSendCommand.restype    = u32; sdk.EdsSendCommand.argtypes    = [vp, u32, i32]
sdk.EdsGetDirectoryItemInfo.restype = u32; sdk.EdsGetDirectoryItemInfo.argtypes = [vp, ctypes.POINTER(EdsDirectoryItemInfo)]
sdk.EdsCreateFileStream.restype = u32; sdk.EdsCreateFileStream.argtypes = [ctypes.c_char_p, u32, u32, pvp]
sdk.EdsDownload.restype       = u32; sdk.EdsDownload.argtypes       = [vp, u64, vp]
sdk.EdsDownloadComplete.restype = u32; sdk.EdsDownloadComplete.argtypes = [vp]
sdk.EdsDownloadCancel.restype  = u32; sdk.EdsDownloadCancel.argtypes  = [vp]

# EdsSetCapacity passes EdsCapacity BY VALUE (not a pointer)
class EdsCapacity(ctypes.Structure):
    _fields_ = [
        ("numberOfFreeClusters", ctypes.c_int32),
        ("bytesPerSector",       ctypes.c_int32),
        ("reset",                ctypes.c_int32),   # EdsBool
    ]
sdk.EdsSetCapacity.restype  = u32
sdk.EdsSetCapacity.argtypes = [vp, EdsCapacity]

# ── Constants ─────────────────────────────────────────────────────────────────

EDS_ERR_OK                               = 0x00000000
EDS_ERR_DEVICE_BUSY                      = 0x00000081
kEdsPropID_SaveTo                        = 0x0000000b   # confirmed from EDSDKTypes.h
kEdsSaveTo_Host                          = 2
kEdsCameraCommand_PressShutterButton     = 0x00000004
kEdsCameraCommand_ShutterButton_OFF      = 0x00000000
kEdsCameraCommand_ShutterButton_Completely_NonAF = 0x00010003
kEdsObjectEvent_All                      = 0x00000200
kEdsObjectEvent_DirItemCreated           = 0x00000203
kEdsObjectEvent_DirItemRemoved           = 0x00000204
kEdsObjectEvent_DirItemRequestTransfer   = 0x00000207
kEdsObjectEvent_DirItemRequestTransferDT = 0x00000208
kEdsFileCreateDisposition_CreateAlways = 1
kEdsAccess_ReadWrite                = 2

EVENT_NAMES = {
    0x00000201: "VolumeInfoChanged",
    0x00000202: "VolumeUpdateItems",
    0x00000203: "DirItemCreated",
    0x00000204: "DirItemRemoved",
    0x00000205: "DirItemInfoChanged",
    0x00000206: "DirItemContentChanged",
    0x00000207: "DirItemRequestTransfer",
    0x00000208: "DirItemRequestTransferDT",
    0x0000020A: "VolumeAdded",
    0x0000020B: "VolumeRemoved",
}

# ── Globals shared with callback ──────────────────────────────────────────────

g_dir_item_ref = None   # set by callback, consumed by main thread
g_event_fired  = False

OBJECT_CB_TYPE = ctypes.WINFUNCTYPE(u32, u32, vp, vp)

def on_object_event(event, obj_ref, context):
    global g_dir_item_ref, g_event_fired
    name = EVENT_NAMES.get(event, f"0x{event:08X}")
    print(f"  [callback] {name}  obj_ref={obj_ref}")
    if event in (kEdsObjectEvent_DirItemCreated,
               kEdsObjectEvent_DirItemRequestTransfer,
               kEdsObjectEvent_DirItemRequestTransferDT) and obj_ref:
        g_dir_item_ref = ctypes.c_void_p(obj_ref)
        g_event_fired = True
        # Do NOT download here — that blocks inside PumpWaitingMessages
    elif obj_ref:
        sdk.EdsRelease(ctypes.c_void_p(obj_ref))
    return EDS_ERR_OK

obj_event_cb = OBJECT_CB_TYPE(on_object_event)

# ── Step 1: Init SDK ──────────────────────────────────────────────────────────

err = sdk.EdsInitializeSDK()
print(f"[3] EdsInitializeSDK: 0x{err:08X} {'OK' if err == 0 else 'FAIL'}")
assert err == EDS_ERR_OK

# ── Step 2: Find camera ───────────────────────────────────────────────────────

camera_list = ctypes.c_void_p()
err = sdk.EdsGetCameraList(ctypes.byref(camera_list))
print(f"[4] EdsGetCameraList: 0x{err:08X}")
assert err == EDS_ERR_OK

count = ctypes.c_uint32(0)
sdk.EdsGetChildCount(camera_list, ctypes.byref(count))
print(f"[5] Cameras found: {count.value}")
assert count.value > 0, "No camera found. Connect the camera and set USB mode to PC Remote."

camera_ref = ctypes.c_void_p()
err = sdk.EdsGetChildAtIndex(camera_list, 0, ctypes.byref(camera_ref))
sdk.EdsRelease(camera_list)
print(f"[6] EdsGetChildAtIndex: 0x{err:08X}")
assert err == EDS_ERR_OK

# ── Step 3: Open session ──────────────────────────────────────────────────────

err = sdk.EdsOpenSession(camera_ref)
print(f"[7] EdsOpenSession: 0x{err:08X} {'OK' if err == 0 else 'FAIL - close EOS Utility?'}")
assert err == EDS_ERR_OK

try:
    # ── Step 4: Configure save-to-host + capacity ─────────────────────────────

    save_to = ctypes.c_uint32(kEdsSaveTo_Host)
    err = sdk.EdsSetPropertyData(camera_ref, kEdsPropID_SaveTo, 0,
                                  ctypes.sizeof(save_to), ctypes.byref(save_to))
    print(f"[8] SetPropertyData(SaveTo=Host): 0x{err:08X} {'OK' if err == 0 else 'WARN'}")

    # Required when SaveTo=Host: tell the camera how much free space the PC has.
    cap = EdsCapacity()
    cap.numberOfFreeClusters = 0x7FFFFFFF
    cap.bytesPerSector       = 512
    cap.reset                = 1
    err = sdk.EdsSetCapacity(camera_ref, cap)
    print(f"[8b] EdsSetCapacity: 0x{err:08X} {'OK' if err == 0 else 'FAIL'}")

    # ── Step 5: Register event handler ───────────────────────────────────────

    err = sdk.EdsSetObjectEventHandler(camera_ref, kEdsObjectEvent_All,
                                        obj_event_cb, None)
    print(f"[9] SetObjectEventHandler: 0x{err:08X}")

    # ── Step 6: Capture ───────────────────────────────────────────────────────

    input("\n[10] Ready to capture. Press Enter to fire the shutter...")

    # Retry on DEVICE_BUSY (normal transient after session open)
    # Canon's own sample retries immediately on 0x81.
    for attempt in range(10):
        err = sdk.EdsSendCommand(camera_ref, kEdsCameraCommand_PressShutterButton,
                                  kEdsCameraCommand_ShutterButton_Completely_NonAF)
        if err != EDS_ERR_DEVICE_BUSY:
            break
        print(f"  DEVICE_BUSY, retrying ({attempt+1}/10)...")
        time.sleep(0.2)
    # Always release the button after pressing
    sdk.EdsSendCommand(camera_ref, kEdsCameraCommand_PressShutterButton,
                        kEdsCameraCommand_ShutterButton_OFF)
    print(f"[11] PressShutterButton(CompletelyNonAF): 0x{err:08X} {'OK' if err == 0 else 'FAIL'}")
    if err != EDS_ERR_OK:
        raise RuntimeError(f"ShutterButton command failed: 0x{err:08X}")

    # ── Step 7: Pump messages until callback fires ────────────────────────────

    print("[12] Waiting for DirItemCreated event (pumping messages)...")
    deadline = time.monotonic() + 30.0
    while not g_event_fired:
        win32gui.PumpWaitingMessages()
        if time.monotonic() > deadline:
            print("TIMEOUT: no image received within 30 s")
            break
        time.sleep(0.01)

    if not g_event_fired:
        print("ERROR: camera did not send an image.")
    else:
        print("[13] Event received! Downloading image...")

        # ── Step 8: Download ─────────────────────────────────────────────────

        output_path = Path(__file__).parent / "test_capture.jpg"
        info = EdsDirectoryItemInfo()
        err = sdk.EdsGetDirectoryItemInfo(g_dir_item_ref, ctypes.byref(info))
        print(f"  EdsGetDirectoryItemInfo: 0x{err:08X}  filename={info.szFileName}  size={info.size}")

        stream = ctypes.c_void_p()
        err = sdk.EdsCreateFileStream(str(output_path).encode("mbcs"),
                                       kEdsFileCreateDisposition_CreateAlways,
                                       kEdsAccess_ReadWrite,
                                       ctypes.byref(stream))
        print(f"  EdsCreateFileStream: 0x{err:08X}")

        err = sdk.EdsDownload(g_dir_item_ref, info.size, stream)
        print(f"  EdsDownload: 0x{err:08X}")

        err = sdk.EdsDownloadComplete(g_dir_item_ref)
        print(f"  EdsDownloadComplete: 0x{err:08X}")

        sdk.EdsRelease(stream)
        sdk.EdsRelease(g_dir_item_ref)

        if output_path.exists():
            print(f"[14] SUCCESS — saved {output_path}  ({output_path.stat().st_size // 1024} KB)")
        else:
            print("[14] ERROR: file was not written to disk")

finally:
    # ── Cleanup — always runs even if an exception is raised ─────────────────
    sdk.EdsCloseSession(camera_ref)
    sdk.EdsRelease(camera_ref)
    sdk.EdsTerminateSDK()
    print("[15] SDK terminated. Done.")
