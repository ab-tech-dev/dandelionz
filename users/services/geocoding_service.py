from typing import Optional, Tuple
import requests
from django.conf import settings


GEOAPIFY_BASE_URL = "https://api.geoapify.com/v1/geocode/search"


def geocode_address(address: str, country_code: Optional[str] = None) -> Optional[Tuple[float, float]]:
    if not address:
        return None

    api_key = getattr(settings, "GEOAPIFY_API_KEY", None)
    if not api_key:
        return None

    params = {
        "format": "json",
        "text": address,
        "limit": 1,
        "apiKey": api_key,
    }

    if country_code:
        params["filter"] = f"countrycode:{country_code}"

    try:
        response = requests.get(GEOAPIFY_BASE_URL, params=params, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        results = data.get("results") or []
        if not results:
            return None
        top = results[0]
        if country_code:
            result_country_code = (top.get("country_code") or "").lower()
            if result_country_code and result_country_code != country_code.lower():
                return None
        lat = top.get("lat")
        lon = top.get("lon")
        if lat is None or lon is None:
            return None
        lat = float(lat)
        lon = float(lon)
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        return lat, lon
    except Exception:
        return None
