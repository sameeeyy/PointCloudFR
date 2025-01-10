# 🛰️ NuageFR

> Download French IGN LiDAR data directly from QGIS with ease

NuageFR is a QGIS plugin that streamlines the process of downloading and processing LiDAR point cloud data from IGN (French National Geographic Institute). Draw your area of interest, click download, and get your data - it's that simple.

![Plugin Interface](/interface.png)

## ✨ Key Features

- **Simple AOI Selection** - Use any polygon layer to define your download area
- **Smart Downloads** - Automatically identifies and downloads required LiDAR tiles
- **Parallel Processing** - Downloads multiple tiles simultaneously for better performance
- **Merge Options** - Three strategies for handling multiple tiles:
  - Use Closest Tile
  - Merge All Intersecting (ideal for automated workflows in QGIS Model Builder)
  - Use Most Coverage
- **Automatic Setup** - Handles all dependencies installation automatically
- 
## 🚀 Installation

1. **Download Plugin**
   - Download `NuageFR.zip` from the [releases page]([https://github.com/sameeeyy/NuageFR/releases])
   - Or clone and zip the repository:
     ```bash
     git clone https://github.com/yourusername/NuageFR.git
     cd NuageFR
     zip -r NuageFR.zip nuagefr/
     ```

2. **Install in QGIS**
   - Open QGIS
   - Go to `Plugins → Manage and Install Plugins → Install from ZIP`
   - Browse to your downloaded `NuageFR.zip`
   - Click `Install Plugin`
   - Enable the plugin if not automatically enabled

3. **Verify Installation**
   - Open the Processing Toolbox (`Processing → Toolbox`)
   - You should see `NuageFR` in the algorithm list

## 🚀 Quick Start

1. **Launch NuageFR**
   ```
   Processing Toolbox → NuageFR → Download LiDAR
   ```

2. **Select Parameters**
   - Choose your AOI layer
   - Set output folder
   - Pick merge strategy
   - Run and get your data!

## 📋 Parameters Explained

Parameter | Description | Example
----------|-------------|--------
Input AOI | Any polygon layer defining your area of interest | Urban district boundary
Output Folder | Where to save downloaded LiDAR data | `C:/LiDAR_Data`
Max Downloads | Number of concurrent downloads (1-10) | `4` (default)
Force Download | Re-download existing files | `False` (default)
Merge Strategy | How to handle multiple tiles | `Use Closest Tile` (default)

## 💡 Tips for Best Results

1. **Optimize AOI Size**
   - Keep areas reasonable (< 100 km²)
   - Split large areas into smaller chunks

2. **Network Performance**
   - Start with 4 concurrent downloads
   - Adjust based on your connection speed

3. **Merge Strategy Selection**
   - Single location: `Use Closest Tile`
   - Full coverage: `Merge All Intersecting` - Particularly useful for automated workflows in QGIS Model Builder as it ensures complete data coverage
   - Large areas: `Use Most Coverage`

## 🤝 Contributing

Found a bug? Have a suggestion? Contributions are welcome!

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## 📝 License

MIT © [Samy KHELIL]

---
<p align="center">
Made with ❤️ for the QGIS community
</p>
