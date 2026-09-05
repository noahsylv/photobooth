Switch Camera from Webcam Streaming to Official Canon Tethering

The current implementation treats the Canon EOS R50 as a webcam/video source (e.g. OpenCV/UVC). This approach does not support the camera's built-in flash because the camera is continuously streaming video rather than taking photographs.

Replace the streaming approach with official Canon tethered capture using Canon's EDSDK (or Canon's official remote capture interface if a newer SDK is available).

Requirements:

Connect the camera to the Beelink via USB-C.
Initialize the Canon SDK and detect the connected camera.
Keep a persistent camera session open for the lifetime of the application.
During the countdown, send a capture command through the SDK instead of grabbing a video frame.
Configure the camera to use its normal photo mode so the built-in flash fires automatically when needed.
After capture, wait for the SDK's image-ready event, download the JPEG to the local session folder, and continue the photobooth workflow.
The rest of the application (countdown, strip generation, printing, Pico communication, etc.) should remain unchanged. Only the camera backend should change.

Create a CameraController abstraction so the rest of the application is independent of the capture method. Example interface:

class CameraController:
    def connect(self): ...
    def start_live_view(self): ...
    def stop_live_view(self): ...
    def capture_photo(self) -> Path: ...
    def disconnect(self): ...

The photobooth application should only call capture_photo(). Whether the implementation uses webcam streaming or Canon tethering should be hidden behind this interface. The Canon tethered implementation should become the default because it supports autofocus, full-resolution images, metadata, and the camera's built-in flash.