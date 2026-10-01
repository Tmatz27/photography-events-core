"""Great-circle parity calculation, never a degrees-to-miles approximation.

Ported from HA wildlife.py at 4905e35c. PostgreSQL stores EPSG:4326; future
metric spatial queries must use geography or an appropriate projected CRS.
"""
import math


def haversine_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((phi2 - phi1) / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        math.radians(lon2 - lon1) / 2
    ) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))

