<div align="center">

# 🛰️ PointCloudFR

**Download French IGN LiDAR data and elevation products directly from QGIS**

[![QGIS Version](https://img.shields.io/badge/QGIS-3.34%20|%204.x-589632?logo=qgis&logoColor=white)](https://qgis.org/)
[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Release](https://img.shields.io/github/v/release/sameeeyy/PointCloudFR)](https://github.com/sameeeyy/PointCloudFR/releases)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://www.python.org)

</div>

<p align="center">
PointCloudFR is a robust QGIS plugin engineered to streamline the acquisition and processing of LiDAR point clouds and elevation rasters from the French National Geographic Institute (IGN). By interfacing in real-time with the IGN Géoplateforme WFS service, it allows professionals to easily download, merge, and visualize highly accurate geospatial data directly within their QGIS environment.
</p>

![Plugin Interface](/interface.png)  

---

## ✨ Key Features

- **Real-Time WFS Integration** - Direct connection to the live IGN Géoplateforme WFS service, ensuring access to the most up-to-date LiDAR tiles.
- **Enterprise Network Compatibility** - Optimized for corporate environments with built-in proxy handling and disabled SSL verification features.
- **QGIS 4 Ready** - Fully compatible with QGIS 3.34+ up to the latest QGIS 4.x versions.
- **Multiple Data Types Supported**:
  - `LIDAR`: Raw classified point cloud data (LAZ)
  - `MNT`: Digital Terrain Model (bare earth elevation)
  - `MNS`: Digital Surface Model (surface with vegetation/buildings)
  - `MNH`: Digital Height Model (object heights above terrain)
- **Smart AOI Selection** - Define your download area using any polygon layer, automatically resolving intersecting tiles in Lambert-93 (EPSG:2154).
- **Advanced Processing Options**:
  - *Download All (No Merge)*: Retrieve raw tiles for custom pipelines via Python/PDAL.
  - *Merge All Intersecting*: Seamlessly combine multiple raster (TIF) tiles into a single seamless layer using GDAL.
  - *Use Most Coverage*: Automatically select the single tile with the maximum overlap.
- **Automated Workflow** - Handles dependency installation behind the scenes and auto-loads datasets (both point clouds with proper classification renderers and continuous rasters) directly into your QGIS project.

## 🚀 Installation

### Option 1: Directly from QGIS Repository (Recommended)
1. Open QGIS.
2. Navigate to `Plugins → Manage and Install Plugins → All`.
3. Search for **PointCloudFR**.
4. Click `Install Plugin`.

### Option 2: Manual Installation from GitHub Releases
1. Download the `PointCloudFR.zip` package from the [Releases page](https://github.com/sameeeyy/PointCloudFR/releases).
2. Open QGIS.
3. Navigate to `Plugins → Manage and Install Plugins → Install from ZIP`.
4. Select the downloaded `PointCloudFR.zip` file.
5. Click `Install Plugin`.

### Option 3: Development / From Source
To install directly from source or compile the package yourself:
```bash
git clone https://github.com/sameeeyy/PointCloudFR
cd PointCloudFR

# Standard installation
python -m setup.py install -fu .

# Install as an editable/live-link (ideal for development)
python -m setup.py install -feu .

# Create the .zip package distribution
python -m setup.py build -u .
```

## 🎯 Quick Start Guide

1. Ensure your Area of Interest (AOI) polygon is loaded in QGIS.
2. Launch the tool from the Menu: `Processing Toolbox → PointCloudFR → Download LiDAR`.
3. Configure the tool:
   - **Input AOI**: Select your polygon layer.
   - **Data Type**: Choose between MNT, MNS, MNH, or LIDAR.
   - **Output Folder**: Specify a directory with sufficient disk space for the files.
   - **Processing Strategy**: Choose your preferred aggregation method.
4. Click **Run**. The plugin will automatically query the IGN WFS server, queue the downloads concurrently, process the files, and load them into the canvas.

## ⚙️ Processing Parameters Reference

| Parameter | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| **Input AOI** | Layer | The bounding geography intersecting desired tiles | *None* |
| **Data Type** | Enum | Topographic product to retrieve (`LIDAR`, `MNT`, `MNS`, `MNH`) | `LIDAR` |
| **Output Folder** | Path | Local directory for storing acquired datasets | *None* |
| **Max Downloads** | Integer | Number of concurrent HTTP connections (1-10) | `4` |
| **Force Download** | Boolean | Ignore cached files and force fresh retrieval | `False` |
| **Processing Strategy** | Enum | Behaviour when confronting multiple tiles (`Download All`, `Merge All`, `Most Coverage`) | `Download All` |
| **Load Layer** | Boolean | Seamlessly inject the processed files into the active QGIS project | `True` |

## 💡 Best Practices

- **Optimize your AOI**: For massive areas (>100 km²), split your geometry into distinct chunks to avoid overwhelming system memory or encountering network timeouts. The recommended maximum per batch is under 50 tiles.
- **Choose the Right Processing Strategy**:
  - *Data Engineering:* Use `Download All` for standalone storage and manual big-data workflows.
  - *Ready-to-use Maps:* Utilize `Merge All Intersecting` for an immediate, unified elevation raster model suitable for analysis.
- **Network Performance**: The default configuration (4 concurrent downloads) generally yields the highest stability, though it may be increased for high-bandwidth connections.

## 🤝 Contributing

We welcome professional contributions, bug reports, and structural ideas.

1. Fork the project repository.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📊 Data Source & Attribution

PointCloudFR retrieves analytical geospatial structures orchestrated by the **French National Geographic Institute (IGN)** through the Géoplateforme APIs.

* **Web Feature Service**: [IGN Géoplateforme WFS (EPSG:2154)](https://data.geopf.fr/wfs/ows)
* **Datasets Leveraged**:
  - `IGNF_MNT-LIDAR-HD:dalle` (Digital Terrain Model)
  - `IGNF_MNS-LIDAR-HD:dalle` (Digital Surface Model)
  - `IGNF_MNH-LIDAR-HD:dalle` (Digital Height Model)
  - `IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle` (LiDAR Point Cloud)

*All intellectual property rights and original topographical responsibilities belong entirely to IGN.*

## 📝 License

Distributed under the **GNU General Public License v3.0**. See `LICENSE` for more information.

---
<div align="center">
Created with ❤️ for the global QGIS community.<br>
<i>In loving memory of Mounir Redjimi, a profoundly inspiring professor.</i>
</div>
