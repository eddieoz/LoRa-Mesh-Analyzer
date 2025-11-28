import sys
import os
import logging
import threading

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Verification")

def verify_utils():
    logger.info("Verifying utils.py...")
    from mesh_analyzer.utils import haversine, get_val, get_node_name
    
    # Test haversine
    dist = haversine(0, 0, 1, 1)
    assert dist > 0, "Haversine calculation failed"
    logger.info(f"Haversine check passed: {dist:.2f}m")
    
    # Test get_val
    obj = {'a': {'b': 1}}
    val = get_val(obj, 'a.b')
    assert val == 1, "get_val nested dict failed"
    
    class TestObj:
        def __init__(self):
            self.x = 10
            self.y = {'z': 20}
            
    obj2 = TestObj()
    val2 = get_val(obj2, 'x')
    assert val2 == 10, "get_val object attr failed"
    val3 = get_val(obj2, 'y.z')
    assert val3 == 20, "get_val object nested dict failed"
    
    logger.info("Utils check passed.")

def verify_modules():
    logger.info("Verifying module imports and instantiation...")
    
    # Mock Interface
    class MockInterface:
        def __init__(self):
            self.nodes = {}
            self.localNode = None
            
    interface = MockInterface()
    
    # Test Analyzer
    from mesh_analyzer.analyzer import NetworkHealthAnalyzer
    analyzer = NetworkHealthAnalyzer()
    issues = analyzer.analyze({})
    assert isinstance(issues, list), "Analyzer did not return list"
    logger.info("Analyzer instantiated and ran.")
    
    # Test ActiveTester
    from mesh_analyzer.active_tests import ActiveTester
    tester = ActiveTester(interface)
    assert hasattr(tester, 'lock'), "ActiveTester missing lock"
    assert isinstance(tester.lock, type(threading.Lock())), "ActiveTester lock is not a Lock"
    logger.info("ActiveTester instantiated and has lock.")
    
    # Test Reporter
    from mesh_analyzer.reporter import NetworkReporter
    reporter = NetworkReporter()
    logger.info("Reporter instantiated.")

if __name__ == "__main__":
    try:
        verify_utils()
        verify_modules()
        print("\nSUCCESS: All verification checks passed!")
    except Exception as e:
        print(f"\nFAILURE: Verification failed: {e}")
        sys.exit(1)
