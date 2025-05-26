import sys
from networking import configure_network
import yt_streamer
import threading
import time

def main():
    try:
        print("Starting Wi-Fi hotspot...")
        print("Launching network portal")
        configure_network()
    except SystemExit:
        pass
            
    print("Wifi configured. Starting YouTube audio streaming server...")
    yt_streamer.run_app()


if __name__ == "__main__":
    main()
