import RPi.GPIO as GPIO
import numpy as np
import threading
import time

class LEDController:
    def __init__(self, led_pins, smoothing=0.8, gain=1.0):
        self.led_pins = led_pins
        self.num_leds = len(led_pins)
        self.smoothing = smoothing
        self.level = 0.0
        self.gain=float(gain)
        self.idle_active = False
        self.idle_thread = None

        GPIO.setmode(GPIO.BCM)
        for pin in self.led_pins:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def compute_rms(self, audio_samples):
        flat = audio_samples.flatten()
        return float(np.sqrt(np.mean(flat ** 2)))

    def update(self, audio_samples):
        rms = self.compute_rms(audio_samples)
        scaled = rms * self.gain
        scaled_clamped = max(0.0, min(scaled, 1.0))
        self.level = self.smoothing * self.level + (1 - self.smoothing) * scaled_clamped
        #level_clamped = max(0.0, min(self.level, 1.0))
        on_count = int(self.level * self.num_leds)

        for idx, pin in enumerate(self.led_pins):
            state = GPIO.HIGH if idx < on_count else GPIO.LOW
            GPIO.output(pin, state)

    def start_idle_animation(self, delay=0.1):
        if self.idle_active:
            return
        self.idle_active = True
        def _animate():
            idx = 0
            while self.idle_active:
                for i, pin in enumerate(self.led_pins):
                    GPIO.output(pin, GPIO.HIGH if i == idx else GPIO.LOW)
                idx = (idx + 1) % self.num_leds
                time.sleep(delay)
            for p in self.led_pins:
                GPIO.output(p, GPIO.LOW)
        self.idle_thread = threading.Thread(target=_animate, daemon=True)
        self.idle_thread.start()

    def stop_idle_animation(self):
        if not self.idle_active:
            return
        self.idle_active = False
        if self.idle_thread:
            self.idle_thread.join()
            self.idle_thread = None

    def cleanup(self):
        GPIO.cleanup()

