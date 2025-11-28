import math
import logging

logger = logging.getLogger(__name__)

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees).
    Returns distance in meters.
    """
    try:
        # Check for None values
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 0

        # convert decimal degrees to radians 
        lon1, lat1, lon2, lat2 = map(math.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

        # haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a)) 
        r = 6371000 # Radius of earth in meters
        return c * r
    except Exception as e:
        logger.debug(f"Error calculating haversine distance: {e}")
        return 0

def get_val(obj: object, key: str, default: any = None) -> any:
    """
    Safely retrieves a value from an object or dictionary.
    Handles nested attribute access if key contains dots (e.g. 'user.id').
    """
    try:
        # Handle dot notation for nested access
        if '.' in key:
            parts = key.split('.')
            current = obj
            for part in parts:
                current = get_val(current, part)
                if current is None:
                    return default
            return current

        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)
    except Exception:
        return default

def get_node_name(node: dict, node_id: str = None) -> str:
    """
    Helper to get a human-readable name for a node.
    """
    user = get_val(node, 'user', {})
    long_name = get_val(user, 'longName')
    short_name = get_val(user, 'shortName')
    
    if long_name:
        return long_name
    if short_name:
        return short_name
    
    # If no name found, return ID
    if node_id:
        return node_id
        
    # Try to find ID in user object
    user_id = get_val(user, 'id')
    if user_id:
        return user_id
        
    return "Unknown"
