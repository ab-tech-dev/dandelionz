"""
Delivery fee calculation using haversine distance (no external API)
"""
from decimal import Decimal
from django.conf import settings
from typing import Dict
from django.core.cache import cache
import hashlib
import math


class DeliveryFeeCalculator:
    """Calculate delivery fees using haversine distance"""

    def __init__(self):
        self.fuel_price = Decimal(str(settings.DELIVERY_FUEL_PRICE_PER_LITER_NGN))
        self.fuel_consumption_per_km = Decimal(str(settings.DELIVERY_FUEL_CONSUMPTION_L_PER_KM))
        self.avg_weight_fee_per_km = Decimal(str(settings.DELIVERY_AVG_WEIGHT_FEE_PER_KM_NGN))
        self.min_fee_ngn = Decimal(str(getattr(settings, "DELIVERY_MIN_FEE_NGN", 0)))
        self.max_fee_ngn = Decimal(str(getattr(settings, "DELIVERY_MAX_FEE_NGN", 0)))
        self.max_distance_miles = settings.DELIVERY_MAX_DISTANCE_MILES
        self.enforce_max_distance = getattr(settings, "DELIVERY_ENFORCE_MAX_DISTANCE", False)
        self.avg_speed_kmph = Decimal(str(settings.DELIVERY_AVG_SPEED_KMPH))

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
            cache_key = self._create_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
            cached_result = cache.get(cache_key)
            if cached_result:
                cached_result['cached'] = True
                return cached_result

            distance_km = self._haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
            distance_miles = distance_km * 0.621371

            if (
                self.enforce_max_distance
                and self.max_distance_miles
                and distance_miles > self.max_distance_miles
            ):
                result = {
                    'success': False,
                    'error': f'Delivery address is outside our {self.max_distance_miles} mile radius',
                    'fee': None,
                    'distance': f"{distance_km:.2f} km",
                    'duration': self._format_duration(distance_km),
                    'distance_miles': round(distance_miles, 2),
                    'cached': False
                }
                return result

            cost_per_km = (self.fuel_consumption_per_km * self.fuel_price) + self.avg_weight_fee_per_km
            raw_fee = Decimal(str(distance_km)) * cost_per_km

            # Apply pricing guard rails to avoid extreme delivery charges.
            if self.min_fee_ngn > 0:
                raw_fee = max(raw_fee, self.min_fee_ngn)
            if self.max_fee_ngn > 0:
                raw_fee = min(raw_fee, self.max_fee_ngn)

            fee = raw_fee.quantize(Decimal('0.01'))

            result = {
                'success': True,
                'fee': float(fee),
                'distance': f"{distance_km:.2f} km",
                'duration': self._format_duration(distance_km),
                'distance_miles': round(distance_miles, 2),
                'error': None,
                'cached': False
            }

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

    def calculate_multiple_fees(
        self,
        origin_lat: float,
        origin_lng: float,
        destinations: list
    ) -> list:
        """
        Calculate fees for multiple destinations without external API.
        """
        if len(destinations) > 100:
            raise ValueError("Maximum 100 destinations allowed")

        results = []

        for idx, (lat, lng) in enumerate(destinations):
            distance_km = self._haversine_km(origin_lat, origin_lng, lat, lng)
            distance_miles = distance_km * 0.621371

            cost_per_km = (self.fuel_consumption_per_km * self.fuel_price) + self.avg_weight_fee_per_km
            raw_fee = Decimal(str(distance_km)) * cost_per_km
            if self.min_fee_ngn > 0:
                raw_fee = max(raw_fee, self.min_fee_ngn)
            if self.max_fee_ngn > 0:
                raw_fee = min(raw_fee, self.max_fee_ngn)
            fee = raw_fee.quantize(Decimal('0.01'))

            within_radius = (not self.max_distance_miles) or (distance_miles <= self.max_distance_miles)

            results.append({
                'destination_index': idx,
                'success': within_radius,
                'fee': float(fee) if within_radius else None,
                'distance': f"{distance_km:.2f} km",
                'duration': self._format_duration(distance_km),
                'distance_miles': round(distance_miles, 2),
                'error': None if within_radius else 'Outside delivery radius'
            })

        return results

    def _haversine_km(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float
    ) -> float:
        """Calculate great-circle distance between two points in km."""
        r = 6371.0
        lat1 = math.radians(origin_lat)
        lng1 = math.radians(origin_lng)
        lat2 = math.radians(dest_lat)
        lng2 = math.radians(dest_lng)

        dlat = lat2 - lat1
        dlng = lng2 - lng1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def _format_duration(self, distance_km: float) -> str:
        """Estimate duration based on average speed."""
        if not self.avg_speed_kmph or self.avg_speed_kmph <= 0:
            return ""
        hours = Decimal(str(distance_km)) / self.avg_speed_kmph
        minutes = int((hours * Decimal('60')).quantize(Decimal('1')))
        if minutes < 60:
            return f"{minutes} mins"
        hrs = minutes // 60
        mins = minutes % 60
        if mins == 0:
            return f"{hrs} hr"
        return f"{hrs} hr {mins} mins"

    def _create_cache_key(self, origin_lat, origin_lng, dest_lat, dest_lng):
        """Create a unique cache key for the route"""
        key_string = (
            f"delivery_fee_v2_{origin_lat}_{origin_lng}_{dest_lat}_{dest_lng}_"
            f"{self.fuel_price}_{self.fuel_consumption_per_km}_{self.avg_weight_fee_per_km}_"
            f"{self.min_fee_ngn}_{self.max_fee_ngn}_{self.max_distance_miles}_{self.enforce_max_distance}"
        )
        return hashlib.md5(key_string.encode()).hexdigest()
