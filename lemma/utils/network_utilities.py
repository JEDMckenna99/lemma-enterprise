"""
Network utilities for Lemma peer-to-peer interactions.
Provides tools for peer discovery, health checks, and network management.
"""

import json
import time
import socket
import requests
import logging
import ipaddress
from typing import Dict, Any, List, Set, Optional, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class PeerDiscovery:
    """
    Peer discovery and management for Lemma networks.
    Provides methods for finding and verifying peers in the network.
    """
    
    def __init__(self, node_id: str, node_url: str, 
                 trusted_peers: List[Dict[str, str]] = None, 
                 storage_path: str = None):
        """
        Initialize the peer discovery system.
        
        Args:
            node_id: This node's identifier (typically a DID)
            node_url: The public URL of this node
            trusted_peers: Initial list of trusted peers with id and url
            storage_path: Path to store peer information
        """
        self.node_id = node_id
        self.node_url = node_url
        self.peers = {}  # peer_id -> peer_info
        self.last_health_check = {}  # peer_id -> timestamp
        self.unreachable_count = {}  # peer_id -> count of failures
        
        # Add trusted peers
        if trusted_peers:
            for peer in trusted_peers:
                if 'id' in peer and 'url' in peer:
                    self.peers[peer['id']] = {
                        'url': peer['url'],
                        'first_seen': time.time(),
                        'last_seen': time.time(),
                        'status': 'trusted',
                        'features': peer.get('features', []),
                        'network': peer.get('network', 'main')
                    }
        
        # Track discovered features
        self.supported_features = {
            'revocation': True,
            'did_resolver': True,
            'zero_knowledge': True,
            'hardware_security': True
        }
        
    def add_peer(self, peer_id: str, peer_url: str, status: str = 'discovered', 
                 features: List[str] = None, network: str = 'main') -> bool:
        """
        Add a peer to the network.
        
        Args:
            peer_id: The peer's identifier (typically a DID)
            peer_url: The peer's URL
            status: Status of the peer (trusted, discovered, etc.)
            features: List of features supported by the peer
            network: Network this peer belongs to (main, test, etc.)
            
        Returns:
            bool: True if the peer was added, False if it was already known
        """
        if peer_id in self.peers:
            # Update existing peer
            self.peers[peer_id]['last_seen'] = time.time()
            # Only update URL if it changed
            if self.peers[peer_id]['url'] != peer_url:
                self.peers[peer_id]['url'] = peer_url
                logger.info(f"Updated peer {peer_id} URL to {peer_url}")
            
            # Update features if provided
            if features:
                self.peers[peer_id]['features'] = features
                
            return False
        else:
            # Add new peer
            self.peers[peer_id] = {
                'url': peer_url,
                'first_seen': time.time(),
                'last_seen': time.time(),
                'status': status,
                'features': features or [],
                'network': network
            }
            
            logger.info(f"Added new peer {peer_id} at {peer_url}")
            return True
            
    def remove_peer(self, peer_id: str) -> bool:
        """
        Remove a peer from the network.
        
        Args:
            peer_id: The peer's identifier
            
        Returns:
            bool: True if the peer was removed, False if it wasn't found
        """
        if peer_id in self.peers:
            del self.peers[peer_id]
            if peer_id in self.last_health_check:
                del self.last_health_check[peer_id]
            if peer_id in self.unreachable_count:
                del self.unreachable_count[peer_id]
            logger.info(f"Removed peer {peer_id}")
            return True
        return False
    
    def get_active_peers(self, max_unreachable: int = 3, feature: str = None) -> List[Dict[str, Any]]:
        """
        Get a list of active peers that meet the criteria.
        
        Args:
            max_unreachable: Maximum number of unreachable attempts
            feature: Optional feature the peers must support
            
        Returns:
            List of active peer information
        """
        active_peers = []
        
        for peer_id, peer_info in self.peers.items():
            # Skip peers with too many unreachable attempts
            if self.unreachable_count.get(peer_id, 0) > max_unreachable:
                continue
                
            # Skip peers that don't support the requested feature
            if feature and feature not in peer_info.get('features', []):
                continue
                
            # Include peer's ID in the returned info
            peer_data = peer_info.copy()
            peer_data['id'] = peer_id
            active_peers.append(peer_data)
            
        return active_peers
    
    def discover_local_network(self, port: int = 5000, timeout: int = 2) -> List[Dict[str, Any]]:
        """
        Discover Lemma nodes on the local network.
        This is a simplified implementation for demonstration purposes.
        
        Args:
            port: Port to check
            timeout: Connection timeout in seconds
            
        Returns:
            List of discovered peers
        """
        discovered = []
        
        try:
            # Get local IP address
            local_ip = socket.gethostbyname(socket.gethostname())
            
            # Extract network prefix
            ip_obj = ipaddress.ip_address(local_ip)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                # For IPv4, scan /24 subnet
                network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
                scan_list = list(network.hosts())
            else:
                # For IPv6, scan /64 subnet (limited to first 100 addresses for speed)
                network = ipaddress.IPv6Network(f"{local_ip}/64", strict=False)
                scan_list = list(network.hosts())[:100]
            
            # Scan IP addresses in the subnet
            for ip in scan_list:
                ip_str = str(ip)
                if ip_str == local_ip:
                    continue  # Skip own IP
                    
                try:
                    url = f"http://{ip_str}:{port}/api/health"
                    response = requests.get(url, timeout=timeout)
                    
                    if response.status_code == 200 and 'lemma' in response.text.lower():
                        # This might be a Lemma node, try to get its node ID
                        logger.info(f"Discovered potential Lemma node at {ip_str}:{port}")
                        
                        # Try to get node info
                        info_url = f"http://{ip_str}:{port}/api/node_info"
                        info_response = requests.get(info_url, timeout=timeout)
                        
                        if info_response.status_code == 200:
                            node_info = info_response.json()
                            peer_id = node_info.get('node_id')
                            
                            if peer_id and peer_id != self.node_id:
                                peer_url = f"http://{ip_str}:{port}"
                                features = node_info.get('features', [])
                                network = node_info.get('network', 'main')
                                
                                self.add_peer(peer_id, peer_url, 'discovered', features, network)
                                discovered.append({
                                    'id': peer_id,
                                    'url': peer_url,
                                    'features': features,
                                    'network': network
                                })
                except requests.RequestException:
                    # Connection failed or timed out, not a Lemma node or not responding
                    pass
        except Exception as e:
            logger.error(f"Error during local network discovery: {e}")
            
        return discovered
    
    def check_peer_health(self, peer_id: str) -> Dict[str, Any]:
        """
        Check if a peer is healthy and responsive.
        
        Args:
            peer_id: The peer's identifier
            
        Returns:
            Dict with health check results
        """
        if peer_id not in self.peers:
            return {'status': 'unknown', 'error': 'Peer not found'}
            
        peer_url = self.peers[peer_id]['url']
        
        try:
            # Update health check timestamp
            self.last_health_check[peer_id] = time.time()
            
            # Check the peer's health endpoint
            health_url = f"{peer_url}/api/health"
            if not health_url.startswith(('http://', 'https://')):
                health_url = f"https://{health_url}"
                
            response = requests.get(health_url, timeout=5)
            
            if response.status_code == 200:
                # Reset unreachable count
                self.unreachable_count[peer_id] = 0
                
                # Update last seen timestamp
                self.peers[peer_id]['last_seen'] = time.time()
                
                return {
                    'peer_id': peer_id,
                    'status': 'healthy',
                    'response_time': response.elapsed.total_seconds(),
                    'timestamp': time.time()
                }
            else:
                # Increment unreachable count
                self.unreachable_count[peer_id] = self.unreachable_count.get(peer_id, 0) + 1
                
                return {
                    'peer_id': peer_id,
                    'status': 'unhealthy',
                    'http_status': response.status_code,
                    'unreachable_count': self.unreachable_count[peer_id],
                    'timestamp': time.time()
                }
        except Exception as e:
            # Increment unreachable count
            self.unreachable_count[peer_id] = self.unreachable_count.get(peer_id, 0) + 1
            
            return {
                'peer_id': peer_id,
                'status': 'unreachable',
                'error': str(e),
                'unreachable_count': self.unreachable_count[peer_id],
                'timestamp': time.time()
            }
    
    def check_all_peers_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Check the health of all known peers.
        
        Returns:
            Dict mapping peer IDs to health check results
        """
        results = {}
        
        for peer_id in list(self.peers.keys()):
            results[peer_id] = self.check_peer_health(peer_id)
            
        return results
    
    def sync_with_trusted_peer(self, peer_id: str) -> Dict[str, Any]:
        """
        Synchronize peer list with a trusted peer.
        
        Args:
            peer_id: The trusted peer's identifier
            
        Returns:
            Dict with synchronization results
        """
        if peer_id not in self.peers:
            return {'status': 'failed', 'error': 'Peer not found'}
            
        # Get the peer's URL
        peer_url = self.peers[peer_id]['url']
        
        try:
            # Get the peer's known peers
            peers_url = f"{peer_url}/api/peers"
            if not peers_url.startswith(('http://', 'https://')):
                peers_url = f"https://{peers_url}"
                
            response = requests.get(peers_url, timeout=10)
            
            if response.status_code != 200:
                return {
                    'status': 'failed',
                    'error': f"HTTP error {response.status_code}",
                    'timestamp': time.time()
                }
                
            peer_data = response.json()
            peers_list = peer_data.get('peers', [])
            
            # Count of peers added
            added_count = 0
            updated_count = 0
            
            # Add new peers from the list
            for p in peers_list:
                if 'id' in p and 'url' in p and p['id'] != self.node_id:
                    status = 'discovered' if p.get('status') == 'trusted' else p.get('status', 'discovered')
                    
                    if self.add_peer(
                        p['id'], 
                        p['url'], 
                        status, 
                        p.get('features', []), 
                        p.get('network', 'main')
                    ):
                        added_count += 1
                    else:
                        updated_count += 1
            
            return {
                'status': 'success',
                'added': added_count,
                'updated': updated_count,
                'total_peers': len(self.peers),
                'timestamp': time.time()
            }
                
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': time.time()
            }
    
    def get_peer_list(self, include_stats: bool = False) -> Dict[str, Any]:
        """
        Get a list of all known peers with their information.
        
        Args:
            include_stats: Whether to include health statistics
            
        Returns:
            Dict with peer information
        """
        peers_list = []
        
        for peer_id, peer_info in self.peers.items():
            peer_data = peer_info.copy()
            peer_data['id'] = peer_id
            
            if include_stats:
                peer_data['last_health_check'] = self.last_health_check.get(peer_id)
                peer_data['unreachable_count'] = self.unreachable_count.get(peer_id, 0)
                
            peers_list.append(peer_data)
            
        return {
            'node_id': self.node_id,
            'node_url': self.node_url,
            'peers': peers_list,
            'count': len(peers_list),
            'timestamp': time.time()
        }
            
# Global peer discovery instance
_peer_discovery = None

def get_peer_discovery(node_id: str = None, node_url: str = None, 
                      trusted_peers: List[Dict[str, str]] = None) -> PeerDiscovery:
    """Get the peer discovery instance."""
    global _peer_discovery
    if _peer_discovery is None and node_id is not None and node_url is not None:
        _peer_discovery = PeerDiscovery(node_id, node_url, trusted_peers)
    return _peer_discovery

def init_peer_discovery(node_id: str, node_url: str, 
                        trusted_peers: List[Dict[str, str]] = None) -> PeerDiscovery:
    """Initialize the peer discovery system."""
    global _peer_discovery
    _peer_discovery = PeerDiscovery(node_id, node_url, trusted_peers)
    return _peer_discovery 