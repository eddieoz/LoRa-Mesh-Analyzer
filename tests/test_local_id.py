#!/usr/bin/env python3
"""
Test script to verify local node ID retrieval from Meshtastic interface.
This test connects to the actual hardware and checks if we can retrieve the local node ID.
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from meshtastic import serial_interface
import time

def test_local_id_retrieval():
    """Test that we can retrieve and convert the local node ID correctly."""
    print("Connecting to Meshtastic node...")
    interface = serial_interface.SerialInterface()
    
    # Wait for connection to stabilize
    time.sleep(2)
    
    print("\n=== Testing Local Node ID Retrieval ===")
    
    # Test 1: Check myInfo exists
    print(f"\n1. myInfo exists: {hasattr(interface, 'myInfo')}")
    if hasattr(interface, 'myInfo'):
        print(f"   myInfo type: {type(interface.myInfo)}")
        print(f"   myInfo content: {interface.myInfo}")
    
    # Test 2: Get my_node_num
    my_node_num = None
    if hasattr(interface, 'myInfo') and interface.myInfo:
        my_node_num = getattr(interface.myInfo, 'my_node_num', None)
        print(f"\n2. my_node_num: {my_node_num}")
        
        # Expected value
        expected_num = 1119572084
        if my_node_num == expected_num:
            print(f"   ✓ PASS: Got expected node number {expected_num}")
        else:
            print(f"   ✗ FAIL: Expected {expected_num}, got {my_node_num}")
    else:
        print("\n2. ✗ FAIL: Could not access myInfo")
    
    # Test 3: Convert to hex ID
    if my_node_num:
        local_id = f"!{my_node_num:08x}"
        print(f"\n3. Converted ID: {local_id}")
        
        expected_id = "!42bb5074"
        if local_id == expected_id:
            print(f"   ✓ PASS: Got expected ID {expected_id}")
        else:
            print(f"   ✗ FAIL: Expected {expected_id}, got {local_id}")
    else:
        print("\n3. ✗ FAIL: Could not convert (no node number)")
    
    # Test 4: Check localNode fallback
    print(f"\n4. localNode exists: {hasattr(interface, 'localNode')}")
    if hasattr(interface, 'localNode') and interface.localNode:
        print(f"   localNode type: {type(interface.localNode)}")
        if hasattr(interface.localNode, 'user'):
            user_id = getattr(interface.localNode.user, 'id', None)
            print(f"   localNode.user.id: {user_id}")
    
    interface.close()
    print("\n=== Test Complete ===")

if __name__ == '__main__':
    test_local_id_retrieval()
