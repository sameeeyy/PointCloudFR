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
  - Merge All Intersecting
  - Use Most Coverage
- **Automatic Setup** - Handles all dependencies installation automatically

## 🚀 Quick Start

1. **Install the Plugin**
   ```
   QGIS → Plugins → Manage and Install Plugins → Search "NuageFR" → Install
   ```

2. **Launch NuageFR**
   ```
   Processing Toolbox → NuageFR → Download LiDAR
   ```

3. **Select Parameters**
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
   - Full coverage: `Merge All Intersecting`
   - Large areas: `Use Most Coverage`

## 🤝 Contributing

Found a bug? Have a suggestion? Contributions are welcome!

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## 📝 License

MIT © [Your Name]

---
<p align="center">
Made with ❤️ for the QGIS community
</p>
