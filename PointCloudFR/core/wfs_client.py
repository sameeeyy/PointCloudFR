import os
from typing import List

import requests
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
)


def query_wfs_tiles(
    aoi_geometry: QgsGeometry, data_type_code: str, logger
) -> List[dict]:
    """Query WFS service with strict EPSG:2154 projection."""
    try:
        logger.info(f"Querying WFS for data type: {data_type_code}")

        # URL du service WFS de la Géoplateforme IGN
        wfs_url = "https://data.geopf.fr/wfs/ows"

        # 1. Force transformation of input geometry to Lambert-93 (EPSG:2154)
        # This ensures our BBOX matches the native server projection
        aoi_l93 = aoi_geometry
        source_crs = (
            aoi_geometry.sourceCrs() if hasattr(aoi_geometry, "sourceCrs") else None
        )

        # If no CRS is defined, assume 2154, otherwise transform if different
        target_crs = QgsCoordinateReferenceSystem("EPSG:2154")
        if source_crs and source_crs.isValid() and source_crs.authid() != "EPSG:2154":
            logger.info(
                f"Reprojecting search area from {source_crs.authid()} to EPSG:2154"
            )
            transform = QgsCoordinateTransform(
                source_crs,
                target_crs,
                QgsProject.instance(),
            )
            aoi_l93 = QgsGeometry(aoi_geometry)
            aoi_l93.transform(transform)

        # 2. Get bounding box in EPSG:2154
        bbox = aoi_l93.boundingBox()

        # 3. Construct parameters with explicit coordinate reference system
        # The URN 'urn:ogc:def:crs:EPSG::2154' is crucial for WFS 2.0
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAME": data_type_code,
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": "EPSG:2154",  # Explicitly ask for response in Lambert-93
        }

        # BBOX format: minx,miny,maxx,maxy,CRS_URN
        params["BBOX"] = (
            f"{bbox.xMinimum()},{bbox.yMinimum()},"
            f"{bbox.xMaximum()},{bbox.yMaximum()},"
            "urn:ogc:def:crs:EPSG::2154"
        )

        logger.info(f"WFS Query URL: {wfs_url}")
        logger.info(f"BBOX: {params['BBOX']}")

        try:
            # Determine SSL verification from environment (defaults to not verifying to support corporate VPNs)
            verify_ssl = os.environ.get("POINTCLOUDFR_SSL_VERIFY", "0") == "1"
            response = requests.get(
                wfs_url, params=params, timeout=30, verify=verify_ssl
            )
            response.raise_for_status()

            # Parse GeoJSON response
            geojson_data = response.json()
            if "features" not in geojson_data:
                logger.warning("WFS returned valid response but 0 features found.")
                return []

            tiles = []
            for feature in geojson_data["features"]:
                if "properties" in feature:
                    properties = feature["properties"]
                    # The new platform uses 'url' and 'nom' or 'name'
                    # We check both just in case
                    url = properties.get("url")
                    name = properties.get("name", properties.get("nom"))

                    if url and name:
                        tiles.append(
                            {
                                "url": url,
                                "name": name,
                                "geometry": feature.get("geometry"),
                                "properties": properties,
                            }
                        )

            logger.info(f"Found {len(tiles)} tiles intersecting the envelope")
            return tiles

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                logger.error(
                    f"WFS 400 Error. The server rejected the request. "
                    f"Check if layer '{data_type_code}' exists."
                )
            else:
                logger.error(f"HTTP Error during WFS request: {str(e)}")
            return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error during WFS request: {str(e)}")
            return []
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing WFS response: {str(e)}")
            if "response" in locals():
                logger.error(f"Response snippet: {response.text[:200]}")
            return []

    except Exception as e:
        logger.error(f"Critical error querying WFS: {str(e)}")
        return []
