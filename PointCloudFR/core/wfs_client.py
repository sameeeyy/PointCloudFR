import os
import requests
from typing import List
from qgis.core import (
    QgsGeometry,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)

def query_wfs_tiles(aoi_geometry: QgsGeometry, data_type_code: str, logger, territory: dict) -> List[dict]:
    """Query WFS service using the appropriate CRS for the detected territory."""
    try:
        territory_srsname = territory["srsname"]
        territory_urn = territory["urn"]

        logger.info(f"Querying WFS for data type: {data_type_code} (CRS: {territory_srsname})")

        # URL du service WFS de la Géoplateforme IGN
        wfs_url = "https://data.geopf.fr/wfs/ows"

        # 1. Force transformation of input geometry to the territory's native CRS
        # This ensures our BBOX matches the expected server projection
        aoi_native = aoi_geometry
        source_crs = (
            aoi_geometry.sourceCrs() if hasattr(aoi_geometry, "sourceCrs") else None
        )

        target_crs = QgsCoordinateReferenceSystem(territory_srsname)
        if (
            source_crs
            and source_crs.isValid()
            and source_crs.authid() != territory_srsname
        ):
            logger.info(
                f"Reprojecting search area from {source_crs.authid()} to {territory_srsname}"
            )
            transform = QgsCoordinateTransform(
                source_crs,
                target_crs,
                QgsProject.instance(),
            )
            aoi_native = QgsGeometry(aoi_geometry)
            aoi_native.transform(transform)

        # 2. Get bounding box in the territory's native CRS
        bbox = aoi_native.boundingBox()

        # 3. Construct parameters with the territory's coordinate reference system
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAME": data_type_code,
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": territory_srsname,
        }

        # BBOX format: minx,miny,maxx,maxy,CRS_URN
        params["BBOX"] = (
            f"{bbox.xMinimum()},{bbox.yMinimum()},"
            f"{bbox.xMaximum()},{bbox.yMaximum()},"
            f"{territory_urn}"
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
                logger.warning(
                    "WFS returned valid response but 0 features found."
                )
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
