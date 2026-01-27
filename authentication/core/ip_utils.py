"""
Utility functions for extracting client IP addresses.
Handles both direct connections and proxied requests (nginx, load balancers, etc.)
"""


def get_client_ip(request_meta):
    """
    Extract client IP address from request metadata.
    
    Handles:
    - Direct connections (REMOTE_ADDR)
    - Proxied requests (X-Forwarded-For header)
    - Cloudflare (CF-Connecting-IP header)
    
    Args:
        request_meta (dict): The request.META dictionary from Django request object
        
    Returns:
        str: Client IP address or empty string if unable to determine
        
    Example:
        ip = get_client_ip(request.META)
        logger.info(f"User login from IP: {ip}")
    """
    
    # Try X-Forwarded-For first (most common for proxied requests)
    # Format: "client_ip, proxy_ip, proxy_ip"
    x_forwarded_for = request_meta.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP (the actual client)
        ip = x_forwarded_for.split(',')[0].strip()
        if ip:
            return ip
    
    # Try Cloudflare header
    cf_connecting_ip = request_meta.get('HTTP_CF_CONNECTING_IP')
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    
    # Try standard REMOTE_ADDR (direct connection)
    remote_addr = request_meta.get('REMOTE_ADDR')
    if remote_addr:
        return remote_addr.strip()
    
    # Fallback
    return ""
