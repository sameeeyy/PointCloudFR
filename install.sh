#!/bin/bash
# Installation script for PointCloudFR QGIS Plugin

# Detect QGIS plugin directory based on OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLUGIN_DIR="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PLUGIN_DIR="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    PLUGIN_DIR="$APPDATA/QGIS/QGIS3/profiles/default/python/plugins"
else
    echo "Unknown OS type: $OSTYPE"
    echo "Please manually copy the PointCloudFR folder to your QGIS plugins directory."
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLUGIN_SRC="$SCRIPT_DIR/PointCloudFR"

# Check that plugin source exists
if [ ! -d "$PLUGIN_SRC" ]; then
    echo "Error: Plugin source directory not found: $PLUGIN_SRC"
    exit 1
fi

# Create plugin directory if it doesn't exist
mkdir -p "$PLUGIN_DIR"

# Remove existing installation
if [ -d "$PLUGIN_DIR/PointCloudFR" ]; then
    echo "Removing existing installation..."
    rm -rf "$PLUGIN_DIR/PointCloudFR"
fi

# Copy plugin
echo "Installing PointCloudFR plugin to: $PLUGIN_DIR"
cp -r "$PLUGIN_SRC" "$PLUGIN_DIR/"

# Install Python dependencies into QGIS's Python environment
echo ""
echo "Installing Python dependencies..."
REQUIREMENTS="$PLUGIN_SRC/requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
    # Try to find QGIS Python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "Warning: Python not found in PATH."
        echo "Please install the dependencies manually:"
        echo "  pip install -r $REQUIREMENTS"
        PYTHON_CMD=""
    fi

    if [ -n "$PYTHON_CMD" ]; then
        $PYTHON_CMD -m pip install -r "$REQUIREMENTS" 2>&1
        if [ $? -ne 0 ]; then
            echo ""
            echo "Warning: Some dependencies may not have installed correctly."
            echo "You may need to install them manually with:"
            echo "  pip install -r $REQUIREMENTS"
        else
            echo "Dependencies installed successfully."
        fi
    fi
else
    echo "Warning: requirements.txt not found, skipping dependency installation."
fi

echo ""
echo "============================================================"
echo "Installation complete!"
echo "============================================================"
echo ""
echo "To use the plugin:"
echo "  1. Restart QGIS"
echo "  2. Go to Plugins -> Manage and Install Plugins..."
echo "  3. Enable 'PointCloudFR'"
echo ""
