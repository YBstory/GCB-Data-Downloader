# GCB Data Downloader

A desktop application for downloading data files from [Global Carbon Budget (GCB)](https://mdosullivan.github.io/GCB/).

![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

- 🔍 **Auto Scanning** - Automatically scan all data files from the GCB website using Selenium
- 📁 **Tree View** - Display files in a tree structure with expand/collapse support
- 🎯 **Flexible Selection** - Select all, invert selection, select by folder, exclude downloaded files
- 🔎 **Smart Filtering** - Filter by filename keywords and file types (.nc, .xlsx, .csv, etc.)
- ⚡ **Parallel Downloads** - Support 1-5 concurrent download tasks for faster downloads
- 🔄 **Resume Support** - Automatically track downloaded files for incremental downloads
- 💾 **Caching** - Save/load scan results to avoid repeated scanning
- 📊 **Progress Display** - Real-time download progress, speed, and ETA
- 🔁 **Auto Retry** - Automatically retry failed downloads up to 3 times

## 🌍 About Global Carbon Budget

The [Global Carbon Budget (GCB)](https://globalcarbonbudget.org/) is an annual assessment led by the Global Carbon Project, providing critical updates on global carbon emissions and the carbon cycle. Since 2006, the GCB has been a key resource for understanding CO2 emissions from fossil fuels, land-use changes, and their impact on climate goals.

The GCB dataset includes:
- **Fossil fuel emissions** - CO2 emissions from coal, oil, gas, and cement production
- **Land-use change emissions** - Emissions from deforestation and land management
- **Atmospheric CO2 growth** - Measured atmospheric CO2 concentrations
- **Ocean and land carbon sinks** - Carbon absorbed by oceans and terrestrial ecosystems
- **Country-level data** - Territorial and consumption-based emissions by country

Data files are available in multiple formats including NetCDF (.nc), Excel (.xlsx), and CSV, making them accessible for researchers, policymakers, and educators worldwide.

## 📸 Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│  GCB Data Downloader                                        │
├─────────────────────────────────────────────────────────────┤
│  URL: [https://mdosullivan.github.io/GCB/] [Scan] [Cache]   │
│  Filter: [________] Type: [All ▼]  [Show All] Downloaded: 100│
├──────────────────────────────┬──────────────────────────────┤
│  File List                    │  Download Control            │
│  ├─ 📁 2024                   │  Selected: 50 files (2.5 GB) │
│  │   ├─ 📄 data.nc    150MB   │  Parallel: [3 ▼]            │
│  │   └─ 📄 info.xlsx  2MB     │  [Start] [Stop]              │
│  └─ 📁 2023                   │                              │
│      └─ ...                   │  Overall: ████████░░ 80%     │
│                               │  Task1: file1.nc downloading │
│                               │  Task2: file2.nc done        │
│                               │  Task3: waiting...           │
└──────────────────────────────┴──────────────────────────────┘
```

## 🚀 Quick Start

### Requirements

- Python 3.7+
- Chrome browser (for Selenium scanning)

### Installation

```bash
pip install selenium webdriver-manager requests
```

### Run

```bash
python gcb_downloader.py
```

## 📖 Usage

### 1. Scan Files

1. Confirm the URL (default is the official GCB address)
2. Click the **"Scan Files"** button
3. The program will automatically launch Chrome (headless mode) to scan all downloadable files
4. Scan results are automatically cached upon completion

### 2. Select Files

- **Select All / Deselect All** - Select or deselect all files
- **Invert Selection** - Invert current selection state
- **Exclude Downloaded** - Remove already downloaded files from selection
- **Select Folder** - Right-click a folder to select all files within it
- **Filter** - Use keywords or file type to filter files

### 3. Download Files

1. Set the save directory (default: `GCB_Data`)
2. Choose parallel download count (1-5)
3. Click **"Start Download"**
4. Click **"Stop Download"** anytime to interrupt

### 4. Cache Management

- **Save Cache** - Save scan results to `gcb_file_cache.json`
- **Load Cache** - Load from cache without re-scanning

## 📂 File Description

| File | Description |
|------|-------------|
| `gcb_downloader.py` | Main program |
| `gcb_file_cache.json` | Scan results cache |
| `gcb_downloaded_record.json` | Downloaded files record |
| `gcb_failed_record.json` | Failed downloads record |

## ⚙️ Configuration

Built-in configurable options:

| Option | Default | Description |
|--------|---------|-------------|
| Parallel Downloads | 1 | Number of concurrent downloads (1-5) |
| Max Retries | 3 | Retry count for failed downloads |
| Retry Delay | 1s | Wait time between retries |
| Size Fetch Threads | 50 | Concurrent threads for fetching file sizes |

## 🔧 Tech Stack

- **GUI**: Tkinter
- **Web Scraping**: Selenium + ChromeDriver
- **HTTP Requests**: Requests (with connection pooling)
- **Concurrency**: ThreadPoolExecutor

## 📝 Changelog

### v1.0.0
- ✅ Basic file scanning and downloading
- ✅ Tree-style file browser
- ✅ Parallel download support
- ✅ Caching and record keeping
- ✅ Real-time download progress display
- ✅ Failed download retry mechanism
- ✅ File size preview
- ✅ Downloaded/failed status indicators

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License

## 🙏 Acknowledgments

- [Global Carbon Budget](https://globalcarbonbudget.org/) - Annual carbon emissions data from the Global Carbon Project
- [Global Carbon Project](https://www.globalcarbonproject.org/) - International research collaboration tracking global carbon cycle
- [Selenium](https://www.selenium.dev/) - Web automation
- [webdriver-manager](https://github.com/SergeyPirogov/webdriver_manager) - ChromeDriver auto-management
