"""
Delivery fee calculation using Radar Distance API
"""
import requests
from decimal import Decimal
from django.conf import settings
from typing import Dict, Tuple, Optional
from django.core.cache import cache
import hashlib


class DeliveryFeeCalculator:
    """Calculate delivery fees using Radar Distance API"""
    
    def __init__(self):
        self.api_key = settings.RADAR_API_KEY
        self.base_url = settings.RADAR_API_BASE_URL
        self.base_fee = Decimal(str(settings.DELIVERY_BASE_FEE))
        self.per_mile_rate = Decimal(str(settings.DELIVERY_PER_MILE_RATE))
        self.max_fee = Decimal(str(settings.DELIVERY_MAX_FEE))
        self.max_distance = settings.DELIVERY_MAX_DISTANCE_MILES

    def calculate_fee(
        self, 
        origin_lat: float, 
        origin_lng: float,
        dest_lat: float,
        dest_lng: float
    ) -> Dict:
        """
        Calculate delivery fee based on distance
        
        Args:
            origin_lat: Restaurant/store latitude
            origin_lng: Restaurant/store longitude
            dest_lat: Customer latitude
            dest_lng: Customer longitude
            
        Returns:
            Dictionary with fee, distance, duration, and success status
        """
        try:
            # Create cache key
            cache_key = self._create_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result:
                cached_result['cached'] = True
                return cached_result
            
            # Get distance from Radar API
            distance_data = self._get_distance(
                origin_lat, origin_lng, 
                dest_lat, dest_lng
            )
            
            if not distance_data:
                return {
                    'success': False,
                    'error': 'Unable to calculate route',
                    'fee': None,
                    'distance': None,
                    'duration': None,
                    'cached': False
                }
            
            # Extract distance in feet and convert to miles
            distance_feet = distance_data['distance']['value']
            distance_miles = distance_feet / 5280
            
            # Check if within delivery radius
            if distance_miles > self.max_distance:
                result = {
                    'success': False,
                    'error': f'Delivery address is outside our {self.max_distance} mile radius',
                    'fee': None,
                    'distance': distance_data['distance']['text'],
                    'duration': distance_data['duration']['text'],
                    'distance_miles': round(distance_miles, 2),
                    'cached': False
                }
                return result
            
            # Calculate fee
            fee = self.base_fee + (Decimal(str(distance_miles)) * self.per_mile_rate)
            fee = min(fee, self.max_fee)  # Cap at maximum
            fee = fee.quantize(Decimal('0.01'))  # Round to 2 decimal places
            
            result = {
                'success': True,
                'fee': float(fee),
                'distance': distance_data['distance']['text'],
                'duration': distance_data['duration']['text'],
                'distance_miles': round(distance_miles, 2),
                'error': None,
                'cached': False
            }
            
            # Cache for 24 hours (Radar allows up to 30 days)
            cache.set(cache_key, result, 60 * 60 * 24)
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'fee': None,
                'distance': None,
                'duration': None,
                'cached': False
            }

    def _get_distance(
        self, 
        origin_lat: float, 
        origin_lng: float,
        dest_lat: float,
        dest_lng: float
    ) -> Optional[Dict]:
        """Call Radar Distance API"""
        
        url = f"{self.base_url}/route/distance"
        
        params = {
            'origin': f'{origin_lat},{origin_lng}',
            'destination': f'{dest_lat},{dest_lng}',
            'modes': 'car',
            'units': 'imperial'
        }
        
        headers = {
            'Authorization': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('meta', {}).get('code') == 200:
                return data.get('routes', {}).get('car')
            
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"Radar API Error: {e}")
            return None

    def calculate_multiple_fees(
        self,
        origin_lat: float,
        origin_lng: float,
        destinations: list
    ) -> list:
        """
        Calculate fees for multiple destinations using Matrix API
        
        Args:
            origin_lat: Restaurant/store latitude
            origin_lng: Restaurant/store longitude
            destinations: List of tuples [(lat1, lng1), (lat2, lng2), ...]
            
        Returns:
            List of fee calculation results
        """
        if len(destinations) > 100:
            raise ValueError("Maximum 100 destinations allowed")
        
        # Format destinations for API
        dest_string = '|'.join([f'{lat},{lng}' for lat, lng in destinations])
        
        url = f"{self.base_url}/route/matrix"
        
        params = {
            'origins': f'{origin_lat},{origin_lng}',
            'destinations': dest_string,
            'mode': 'car',
            'units': 'imperial'
        }
        
        headers = {
            'Authorization': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('meta', {}).get('code') != 200:
                return []
            
            results = []
            matrix = data.get('matrix', [[]])[0]  # First origin row
            
            for idx, route_data in enumerate(matrix):
                distance_feet = route_data['distance']['value']
                distance_miles = distance_feet / 5280
                
                # Calculate fee
                fee = self.base_fee + (Decimal(str(distance_miles)) * self.per_mile_rate)
                fee = min(fee, self.max_fee)
                fee = fee.quantize(Decimal('0.01'))
                
                within_radius = distance_miles <= self.max_distance
                
                results.append({
                    'destination_index': idx,
                    'success': within_radius,
                    'fee': float(fee) if within_radius else None,
                    'distance': route_data['distance']['text'],
                    'duration': route_data['duration']['text'],
                    'distance_miles': round(distance_miles, 2),
                    'error': None if within_radius else 'Outside delivery radius'
                })
            
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"Radar Matrix API Error: {e}")
            return []

    def _create_cache_key(self, origin_lat, origin_lng, dest_lat, dest_lng):
        """Create a unique cache key for the route"""
        key_string = f"delivery_fee_{origin_lat}_{origin_lng}_{dest_lat}_{dest_lng}"
        return hashlib.md5(key_string.encode()).hexdigest()
