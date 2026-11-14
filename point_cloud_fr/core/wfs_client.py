from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from qgis.core import QgsGeometry

from ..utils.config import (
    WFS_LAYER_NAME,
    WFS_PAGE_SIZE,
    WFS_URL,
)


def _parse_wfs_features(geojson_data: dict, property_key: str) -> list[dict]:
    """Parse WFS GeoJSON response into tile dicts."""
    tiles = []
    for feature in geojson_data.get("features", []):
        if "properties" not in feature:
            continue
        properties = feature["properties"]
        url = properties.get(property_key)

        if url and isinstance(url, str):
            url = url.strip()
            # Extract clean filename from URL query or path
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            filename_param = None
            for k, v in query_params.items():
                if k.lower() == "filename" and v:
                    filename_param = unquote(v[0])
                    break

            if filename_param:
                name = filename_param
            else:
                name = Path(parsed.path).name

            if not name or name in ("ows", "wms-r", "wfs"):
                coordonnees = properties.get("coordonnees_nw", "unknown")
                name = f"tile_{coordonnees}_{property_key}"

            tiles.append(
                {
                    "url": url,
                    "name": name,
                    "geometry": feature.get("geometry"),
                    "properties": properties,
                }
            )
    return tiles


def query_wfs_tiles(
    aoi_geometry: QgsGeometry,
    property_key: str,
    logger,
    territory: dict,
    proxies: dict = None,
    verify_ssl: bool = True,
) -> list[dict]:
    """Query WFS service with pagination using the appropriate CRS for the detected territory.

    The aoi_geometry must already be projected into the territory's native CRS
    before calling this function.

    Raises RuntimeError on any network or parsing failure: a partial tile list
    would silently produce an incomplete download.
    """
    territory_srsname = territory["srsname"]
    territory_urn = territory["urn"]

    logger.debug(f"WFS query — property: {property_key}, CRS: {territory_srsname}")

    bbox = aoi_geometry.boundingBox()
    bbox_str = (
        f"{bbox.xMinimum()},{bbox.yMinimum()},"
        f"{bbox.xMaximum()},{bbox.yMaximum()},"
        f"{territory_urn}"
    )
    logger.debug(f"BBOX: {bbox_str}")

    # Paginated WFS query (server default limit is 5000)
    all_tiles = []
    start_index = 0

    while True:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAME": WFS_LAYER_NAME,
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": territory_srsname,
            "BBOX": bbox_str,
            "COUNT": WFS_PAGE_SIZE,
            "STARTINDEX": start_index,
        }

        try:
            response = requests.get(
                WFS_URL,
                params=params,
                timeout=30,
                verify=verify_ssl,
                proxies=proxies,
            )
            response.raise_for_status()
            geojson_data = response.json()
            raw_features = geojson_data.get("features", [])
            page_tiles = _parse_wfs_features(geojson_data, property_key)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                raise RuntimeError(
                    f"WFS 400 Error. The server rejected the request. "
                    f"Check if layer '{WFS_LAYER_NAME}' exists."
                ) from e
            raise RuntimeError(f"HTTP Error during WFS request: {e}") from e
        except requests.exceptions.SSLError as e:
            raise RuntimeError(
                f"SSL error during WFS request: {e}\n"
                f"Behind an SSL-inspecting corporate proxy, untick "
                f"'Verify SSL certificates' and run again."
            ) from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Connection error during WFS request: {e}") from e
        except (ValueError, KeyError) as e:
            raise RuntimeError(f"Error parsing WFS response: {e}") from e

        all_tiles.extend(page_tiles)
        logger.debug(
            f"WFS page {start_index // WFS_PAGE_SIZE + 1}: "
            f"{len(raw_features)} raw features, {len(page_tiles)} matching tiles "
            f"(total: {len(all_tiles)})"
        )

        # Stop if server returned fewer results than page size (last page)
        if len(raw_features) < WFS_PAGE_SIZE:
            break

        start_index += WFS_PAGE_SIZE

    logger.debug(f"WFS total: {len(all_tiles)} tiles found")
    return all_tiles
