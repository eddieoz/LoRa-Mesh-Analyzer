"""
Configuration validator for Meshtastic node settings.

This module validates local node configuration and provides warnings
for non-optimal settings.
"""
import logging

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates Meshtastic node configuration."""
    
    @staticmethod
    def check_local_config(interface) -> None:
        """
        Analyzes the local node's configuration and warns about non-optimal settings.
        
        Args:
            interface: The Meshtastic interface object with access to localNode
        """
        logger.info("Checking local node configuration...")
        try:
            # Wait a moment for node to populate if needed (though interface init usually does it)
            node = None
            if hasattr(interface, 'localNode'):
                node = interface.localNode
            
            if not node:
                logger.warning("Could not access local node information.")
                return

            # 1. Check Role
            try:
                # Note: node.config might be a property of the node object
                # In some versions, it's node.localConfig
                if hasattr(node, 'config'):
                    config = node.config
                elif hasattr(node, 'localConfig'):
                    config = node.localConfig
                else:
                    logger.warning("Could not find config attribute on local node.")
                    return

                from meshtastic.protobuf import config_pb2
                role = config.device.role
                role_name = config_pb2.Config.DeviceConfig.Role.Name(role)
                
                if role_name in ['ROUTER', 'ROUTER_CLIENT', 'REPEATER']:
                    logger.warning(f" [!] Local Node Role is '{role_name}'.")
                    logger.warning("     Recommended for monitoring: 'CLIENT' or 'CLIENT_MUTE'.")
                    logger.warning("     (Active monitoring works best when the monitor itself isn't a router)")
                else:
                    logger.info(f"Local Node Role: {role_name} (OK)")
            except Exception as e:
                logger.warning(f"Could not verify role: {e}")

            # 2. Check Hop Limit
            try:
                if hasattr(node, 'config'):
                    config = node.config
                elif hasattr(node, 'localConfig'):
                    config = node.localConfig
                
                hop_limit = config.lora.hop_limit
                if hop_limit > 3:
                    logger.warning(f" [!] Local Node Hop Limit is {hop_limit}.")
                    logger.warning("     Recommended: 3. High hop limits can cause network congestion.")
                else:
                    logger.info(f"Local Node Hop Limit: {hop_limit} (OK)")
            except Exception as e:
                logger.warning(f"Could not verify hop limit: {e}")

        except Exception as e:
            logger.error(f"Failed to check local config: {e}")
