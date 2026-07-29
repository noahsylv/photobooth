from machine import Pin
from time import sleep

button = Pin(15, Pin.IN, Pin.PULL_UP)

while True:
    if not button.value():
        print("Pressed")
        while not button.value():
            sleep(0.01)
    sleep(0.01)