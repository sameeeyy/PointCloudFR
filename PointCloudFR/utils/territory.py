"""
Territory detection and CRS mapping for French overseas territories (DOM-TOM).

Each French territory has its own official coordinate reference system.
This module detects which territory an AOI falls into and returns the
appropriate CRS parameters for WFS queries and geometry operations.
"""

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
)

# Territory definitions with their native CRS and bounding boxes in WGS84 (lon_min, lat_min, lon_max, lat_max)
TERRITORIES = {
    "guadeloupe": {
        "name": "Guadeloupe",
        "epsg": 5490,
        "srsname": "EPSG:5490",
        "urn": "urn:ogc:def:crs:EPSG::5490",
        "bbox_wgs84": (-62.0, 15.8, -60.9, 16.6),
    },
    "martinique": {
        "name": "Martinique",
        "epsg": 5490,
        "srsname": "EPSG:5490",
        "urn": "urn:ogc:def:crs:EPSG::5490",
        "bbox_wgs84": (-61.3, 14.3, -60.8, 14.9),
    },
    "guyane": {
        "name": "Guyane",
        "epsg": 2972,
        "srsname": "EPSG:2972",
        "urn": "urn:ogc:def:crs:EPSG::2972",
        "bbox_wgs84": (-55.0, 2.0, -51.5, 6.0),
    },
    "reunion": {
        "name": "La Réunion",
        "epsg": 2975,
        "srsname": "EPSG:2975",
        "urn": "urn:ogc:def:crs:EPSG::2975",
        "bbox_wgs84": (55.1, -21.5, 55.9, -20.8),
    },
    "mayotte": {
        "name": "Mayotte",
        "epsg": 4471,
        "srsname": "EPSG:4471",
        "urn": "urn:ogc:def:crs:EPSG::4471",
        "bbox_wgs84": (44.9, -13.1, 45.4, -12.5),
    },
    # Metropole is last — used as the default fallback
    "metropole": {
        "name": "France métropolitaine",
        "epsg": 2154,
        "srsname": "EPSG:2154",
        "urn": "urn:ogc:def:crs:EPSG::2154",
        "bbox_wgs84": (-5.5, 41.0, 10.0, 51.5),
    },
}

DEFAULT_TERRITORY = TERRITORIES["metropole"]


def _point_in_bbox(lon: float, lat: float, bbox: tuple) -> bool:
    """Check if a WGS84 point (lon, lat) falls within a bounding box (lon_min, lat_min, lon_max, lat_max)."""
    lon_min, lat_min, lon_max, lat_max = bbox
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def detect_territory(
    aoi_geometry: QgsGeometry, source_crs: QgsCoordinateReferenceSystem, logger=None
) -> dict:
    """
    Detect which French territory an AOI geometry belongs to.

    The detection works by reprojecting the centroid of the AOI to WGS84 (EPSG:4326)
    and checking which territory bounding box contains it. DOM-TOM territories are
    checked first (smaller, more specific boxes), then metropole as fallback.

    Args:
        aoi_geometry: The Area of Interest geometry.
        source_crs: The CRS of the input geometry.
        logger: Optional logger instance for diagnostic messages.

    Returns:
        A territory dictionary containing name, epsg, srsname, urn, and bbox_wgs84.
    """
    try:
        # Reproject centroid to WGS84 for territory detection
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

        centroid_geom = aoi_geometry.centroid()

        if source_crs.isValid() and source_crs.authid() != "EPSG:4326":
            transform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
            centroid_geom.transform(transform)

        centroid_point = centroid_geom.asPoint()
        lon = centroid_point.x()
        lat = centroid_point.y()

        if logger:
            logger.info(f"AOI centroid in WGS84: lon={lon:.4f}, lat={lat:.4f}")

        # Check DOM-TOM territories first (they are more specific),
        # then metropole as the catch-all fallback
        for key, territory in TERRITORIES.items():
            if _point_in_bbox(lon, lat, territory["bbox_wgs84"]):
                if logger:
                    logger.info(
                        f"Detected territory: {territory['name']} "
                        f"(CRS: {territory['srsname']})"
                    )
                return territory

        # If no territory matched, default to metropole with a warning
        if logger:
            logger.warning(
                f"AOI centroid ({lon:.4f}, {lat:.4f}) does not fall within any "
                f"known French territory. Defaulting to France métropolitaine (EPSG:2154)."
            )
        return DEFAULT_TERRITORY

    except Exception as e:
        if logger:
            logger.warning(
                f"Error during territory detection: {e}. "
                f"Defaulting to France métropolitaine (EPSG:2154)."
            )
        return DEFAULT_TERRITORY


def get_native_crs(territory: dict) -> QgsCoordinateReferenceSystem:
    """Return the QgsCoordinateReferenceSystem for a given territory dictionary."""
    return QgsCoordinateReferenceSystem(territory["srsname"])
