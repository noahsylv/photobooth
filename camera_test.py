import cv2
from random import random
from datetime import datetime
from pathlib import Path

output_dir = Path("captures")
output_dir.mkdir(exist_ok=True)

# Try camera index 0 first. If it doesn't work, try 1, 2, etc.
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

if not cap.isOpened():
    raise RuntimeError("Could not open camera. Try changing VideoCapture(0) to 1 or 2.")

print("Press SPACE to save a photo. Press Q to quit.")

while True:
    ok, frame = cap.read()
    if not ok:
        print("Could not read frame.")
        break

    cv2.imshow("Photobooth Camera Test", frame)

    # key = cv2.waitKey(1) & 0xFF
    key = cv2.waitKey(1)

    # if key == ord(" ") or random() < .001:
    if random() < .01:
        filename = output_dir / f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(str(filename), frame)
        gray_image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cv2.imwrite(str(filename).replace(".jpg", "-grap.jpg"), frame)
        print(f"Saved {filename}")

    # elif key == ord("q"):
    #     break

cap.release()
cv2.destroyAllWindows()