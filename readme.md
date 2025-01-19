# 🛰️ PointCloudFR

> Download French IGN LiDAR data directly from QGIS with ease

PointCloudFR is a QGIS plugin that streamlines the process of downloading and processing LiDAR point cloud data from IGN (French National Geographic Institute). Draw your area of interest, click download, and get your data - it's that simple!

![Plugin Interface](/interface.png)

## ✨ Key Features

- **Simple AOI Selection** - Use any polygon layer to define your download area
- **Smart Downloads** - Automatically identifies and downloads required LiDAR tiles
- **Parallel Processing** - Downloads multiple tiles simultaneously for better performance
- **Advanced Error Handling** - Comprehensive error checking and recovery mechanisms
- **Multiple Data Sources** - Uses both IGN's primary server and backup sources for reliability
- **Flexible Processing Options** - Three strategies for handling multiple tiles:
  - Download All (No Merge) - Get all raw tiles for custom processing
  - Merge All Intersecting - Combines all intersecting tiles (ideal for automated workflows)
  - Use Most Coverage - Selects the tile with maximum overlap
- **Automatic Setup** - Handles all dependencies installation automatically
- **Auto-Loading** - Option to automatically load downloaded point clouds into your QGIS project

## 🚀 Installation

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

Parameter | Description | Example
----------|-------------|--------
Input AOI | Any polygon layer defining your area of interest | Urban district boundary
Output Folder | Where to save downloaded LiDAR data | `C:/LiDAR_Data`
Max Downloads | Number of concurrent downloads (1-10) | `4` (default)
Force Download | Re-download existing files | `False` (default)
Processing Strategy | How to handle multiple tiles | `Download All (No Merge)` (default)
Load Layer | Automatically load point cloud after download | `True` (default)

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
   - Use the auto-load option for immediate visualization
   - Disable auto-load for batch processing or when working with many tiles

## 🤝 Contributing

Found a bug? Have a suggestion? Contributions are welcome!

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## Data Source 📊

PointCloudFR relies on a comprehensive database of LiDAR HD IGN tiles distribution. This database is maintained and distributed by Diego Cusicanqui through Zenodo:

* **Database Title**: LiDAR HD IGN tiles distribution
* **Author**: Diego Cusicanqui
* **Year**: 2024
* **Publisher**: Zenodo
* **DOI**: [10.5281/zenodo.13793544](https://doi.org/10.5281/zenodo.13793544)

## 📝 License

MIT © [Samy KHELIL]

---
<p align="center">
Made with ❤️ for the QGIS community \n
In the loving memory of Mounir Redjimi, my dear professor.
</p>
