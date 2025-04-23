# app/utils/geofence.py

from math import radians, sin, cos, sqrt, atan2

def haversine_dist(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000 
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lng2 - lng1)

    a = sin(Δφ/2)**2 + cos(φ1) * cos(φ2) * sin(Δλ/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def is_within_radius(
    lat: float,
    lng: float,
    center_lat: float,
    center_lng: float,
    radius_m: float
) -> bool:

    return haversine_dist(lat, lng, center_lat, center_lng) <= radius_m
