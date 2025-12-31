# boss-is-talking-im-buying

> **Trade during work hours. Because markets don’t care about meetings.**

A stealthy, clean, and efficient stock monitoring tool designed for the modern professional who needs to keep an eye on the market without drawing attention.

## Features

- 📉 **Real-time Data**: Fetches the latest stock data (A-Share) instantly.
- 🤫 **Stealth Mode**: Designed to look like a standard utility or dashboard.
- ⚡ **Lightweight**: Minimal resource usage, perfect for running in the background.
- 🛠 **Easy Configuration**: JSON-based configuration for easy stock management.

## Getting Started

### Prerequisites

- Python 3.8+
- [Anaconda](https://www.anaconda.com/) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (recommended)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/boss-is-talking-im-buying.git
   cd boss-is-talking-im-buying
   ```

2. Create and activate the environment:
   ```bash
   conda create -n stock python=3.10
   conda activate stock
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Quick Start

Simply run the batch file:

```bash
run.bat
```

Or manually:

```bash
python stock_monitor.py
```

### Configuration

Edit `stock_config.json` to add the stocks you want to watch.

```json
{
  "stocks": [
    "600519",
    "000001",
    "002594"
  ]
}
```

## Disclaimer

This tool is for educational purposes only. Trade responsibly and don't get fired.

## License

MIT

