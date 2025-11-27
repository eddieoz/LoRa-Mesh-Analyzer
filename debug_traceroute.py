#!/usr/bin/env python3
"""
Debug script to capture and display traceroute packet structure.
Run this and send a traceroute to see the actual packet format.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from meshtastic import serial_interface
import time
import json

def on_receive(packet, interface):
    """Callback for received packets."""
    try:
        decoded = packet.get('decoded', {})
        portnum = decoded.get('portnum')
        
        if portnum == 'TRACEROUTE_APP':
            print("\n" + "="*80)
            print("TRACEROUTE PACKET RECEIVED")
            print("="*80)
            print(f"\nFrom: {packet.get('fromId')}")
            print(f"To: {packet.get('toId')}")
            print(f"\nFull Packet Structure:")
            print(json.dumps(packet, indent=2, default=str))
            print("\n" + "="*80)
            
            # Check for route fields
            print("\nLooking for route data:")
            print(f"  decoded.route: {decoded.get('route', 'NOT FOUND')}")
            print(f"  decoded.routeBack: {decoded.get('routeBack', 'NOT FOUND')}")
            
            # Check all keys in decoded
            print(f"\nAll keys in decoded: {list(decoded.keys())}")
            
    except Exception as e:
        print(f"Error in callback: {e}")

print("Connecting to Meshtastic...")
interface = serial_interface.SerialInterface()

# Subscribe to receive packets
from pubsub import pub
pub.subscribe(on_receive, "meshtastic.receive")

print("Listening for traceroute packets...")
print("Send a traceroute from another device or use: meshtastic --traceroute <node_id>")
print("Press Ctrl+C to exit")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting...")
    interface.close()
