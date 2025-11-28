
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def parse_packet(packet):
    # Extract route information from traceroute packet
    decoded = packet.get('decoded', {})
    
    logger.debug(f"Decoded packet keys: {list(decoded.keys())}")
    
    # The traceroute data is in decoded['traceroute'] (parsed by library)
    # or in RouteDiscovery protobuf in payload (if raw)
    route = []
    route_back = []
    
    # 1. Check for pre-parsed 'traceroute' dict (Meshtastic python lib does this)
    if 'traceroute' in decoded:
        tr = decoded['traceroute']
        if isinstance(tr, dict):
            route = tr.get('route', [])
            route_back = tr.get('routeBack', [])
            logger.debug(f"Found parsed traceroute: route={route}, route_back={route_back}")
    
    # 2. Fallback: Try to parse RouteDiscovery protobuf from payload
    elif 'payload' in decoded:
        try:
            from meshtastic import mesh_pb2
            # If payload is bytes, parse it
            if isinstance(decoded['payload'], bytes):
                route_discovery = mesh_pb2.RouteDiscovery()
                route_discovery.ParseFromString(decoded['payload'])
                route = list(route_discovery.route)
                route_back = list(route_discovery.route_back)
                logger.debug(f"Parsed from bytes - route: {route}, route_back: {route_back}")
            # If it's already a protobuf object
            elif hasattr(decoded['payload'], 'route'):
                route = list(decoded['payload'].route)
                route_back = list(decoded['payload'].route_back)
                logger.debug(f"Extracted from protobuf - route: {route}, route_back: {route_back}")
        except Exception as e:
            logger.debug(f"Could not parse RouteDiscovery protobuf: {e}")
    
    # 3. Fallback: Old dict keys
    if not route:
        route = decoded.get('route', [])
        route_back = decoded.get('routeBack', [])
        
    return route, route_back

# Real packet data from debug log
packet = {
    'from': 2905093827, 
    'to': 1119572084, 
    'channel': 1, 
    'decoded': {
        'portnum': 'TRACEROUTE_APP', 
        'payload': b'\n\x08s\x81w{Z9\xedW\x12\x15\x16\xf2\xff\xff\xff\xff\xff\xff\xff\xff\x01\xb6\xff\xff\xff\xff\xff\xff\xff\xff\x01\x1a\x04s\x81w{"\x0b\xce\xff\xff\xff\xff\xff\xff\xff\xff\x01\x19', 
        'requestId': 1781248082, 
        'bitfield': 1, 
        'traceroute': {
            'route': [2071429491, 1475164506], 
            'snrTowards': [22, -14, -74], 
            'routeBack': [2071429491], 
            'snrBack': [-50, 25], 
            'raw': "route: 2071429491..."
        }
    }, 
    'id': 4198764725, 
    'rxSnr': 6.25, 
    'hopLimit': 3, 
    'rxRssi': -45, 
    'hopStart': 4, 
    'relayNode': 115, 
    'transportMechanism': 'TRANSPORT_LORA', 
    'fromId': '!ad2836c3', 
    'toId': '!42bb5074'
}

print("Testing parsing...")
r, rb = parse_packet(packet)
print(f"Result: route={r}, route_back={rb}")

if r == [2071429491, 1475164506] and rb == [2071429491]:
    print("SUCCESS! Parsing logic works.")
else:
    print("FAILURE! Parsing logic incorrect.")
