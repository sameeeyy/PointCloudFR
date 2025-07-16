# 🛰️ PointCloudFR

> Download French IGN LiDAR data directly from QGIS with ease

PointCloudFR is a QGIS plugin that streamlines the process of downloading and processing LiDAR point cloud and elevation data from IGN (French National Geographic Institute). Draw your area of interest, select your data type, click download, and get your data - it's that simple!

![Plugin Interface](/interface.png)  

## ✨ Key Features

- **Simple AOI Selection** - Use any polygon layer to define your download area
- **Smart Downloads** - Automatically identifies and downloads required LiDAR tiles
- **Multiple Data Types** - Download LiDAR point clouds or elevation rasters (MNT, MNS, MNH)
- **Flexible Processing Options** - Three strategies for handling multiple tiles:
  - Download All (No Merge) - Get all raw tiles for custom processing
  - Merge All Intersecting - Combines all intersecting tiles (ideal for automated workflows)
  - Use Most Coverage - Selects the tile with maximum overlap
- **Automatic Setup** - Handles all dependencies installation automatically
- **Auto-Loading** - Option to automatically load downloaded layers (point clouds with classified renderer or rasters) into your QGIS project

## 🚀 Installation

### Directly from QGIS
   - Open QGIS
   - Go to `Plugins → Manage and Install Plugins → All`
   - Search & select `PointCloudFR`
   - Click `Install Plugin`

### From GitHub artifacts

1. **Download Plugin**
   - Download `PointCloudFR.zip` from the [releases page](https://github.com/sameeeyy/PointCloudFR/releases)
   - Or clone and zip the repository:
     ```bash
     git clone https://github.com/yourusername/PointCloudFR.git
     cd PointCloudFR
     zip -r PointCloudFR.zip pointcloudfr/
     ```

2. **Install in QGIS**
   - Open QGIS
   - Go to `Plugins → Manage and Install Plugins → Install from ZIP`
   - Browse to your downloaded `PointCloudFR.zip`
   - Click `Install Plugin`
   - Enable the plugin if not automatically enabled

3. **Verify Installation**
   - Open the Processing Toolbox (`Processing → Toolbox`)
   - You should see `PointCloudFR` in the algorithm list
   - A welcome message will appear on first installation

### From Sources

1. **Clone this repo**
```sh
git clone https://github.com/sameeeyy/PointCloudFR
cd PointCloudFR
# regular install
python -m setup.py install -fu .
# install as editable
python -m setup.py install -feu .
# or package zip (see install from artifacts)
python -m setup.py build -u .
```

## 🚀 Quick Start

1. **Launch PointCloudFR**
   ```
   Processing Toolbox → PointCloudFR → Download LiDAR
   ```

2. **Select Parameters**
   - Choose your AOI layer
   - Set output folder
   - Pick processing strategy
   - Configure download options
   - Run and get your data!

## 📋 Parameters Explained

| Parameter | Description | Example |
| :-- | :-- | :-- |
| Input AOI | Any polygon layer defining your area of interest | Urban district boundary |
| Data Type | Type of data to download: MNT (Digital Terrain Model), MNS (Digital Surface Model), MNH (Digital Height Model), or LIDAR (Point Cloud) | `LIDAR (Point Cloud)` (default) |
| Output Folder | Where to save downloaded data | `C:/LiDAR_Data` |
| Max Downloads | Number of concurrent downloads (1-10) | `4` (default) |
| Force Download | Re-download existing files | `False` (default) |
| Processing Strategy | How to handle multiple tiles | `Download All (No Merge)` (default) |
| Load Layer | Automatically load downloaded layers after processing | `True` (default) |


## 💡 Tips for Best Results

1. **Optimize AOI Size**
   - Keep areas reasonable (< 100 km²)
   - Split large areas into smaller chunks

2. **Network Performance**
   - Start with 4 concurrent downloads
   - Adjust based on your connection speed
   - Plugin will automatically retry failed downloads

3. **Processing Strategy Selection**
   - Raw Data Workflow: `Download All (No Merge)` - Perfect when you want to process the raw data yourself
   - Complete Coverage: `Merge All Intersecting` - Ideal for automated workflows in QGIS Model Builder
   - Partial Coverage: `Use Most Coverage` - When you only need the tile with maximum overlap

4. **Data Loading**
    - Use the auto-load option for immediate visualization (point clouds with classification or rasters)
    - Disable auto-load for batch processing or when working with many tiles

## 🤝 Contributing

Found a bug? Have a suggestion? Contributions are welcome!

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## Data Source 📊

PointCloudFR is powered by LiDAR HD and elevation data originally created by the French National Geographic Institute (IGN). This dataset is accessed directly through IGN's Web Feature Service (WFS) via the Géoplateforme.

* **Data Source**: IGN Géoplateforme WFS Service
* **Service URL**: https://data.geopf.fr/wfs/ows
* **Original Creator**: IGN (Institut National de l'Information Géographique et Forestière)
* **Data Types Available**: 
  - IGNF_LIDAR-HD_TA:mnt-dalle (Digital Terrain Model)
  - IGNF_LIDAR-HD_TA:mns-dalle (Digital Surface Model)
  - IGNF_LIDAR-HD_TA:mnh-dalle (Digital Height Model)
  - IGNF_LIDAR-HD_TA:nuage-dalle (LiDAR Point Cloud)
* **Access Method**: Real-time WFS queries

*All intellectual property rights for the original geospatial data are held by IGN.*

## 📝 License

GNU © [Samy KHELIL]

---
<p align="center">
Made with ❤️ for the QGIS community<br>
In the loving memory of Mounir Redjimi, my dear professor.
</p>
