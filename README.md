# boss-is-talking-im-buying

**中文** | [English](README_EN.md)

> **上班摸鱼，下班收米。因为市场不在乎你在开会。**

一款专为当代打工人设计的隐蔽、简洁、高效的股票监控工具。让你在工作中随时掌握市场动态，却不引起任何人的注意。

## 功能特点

- 📉 **实时数据**：秒级获取 A 股最新行情数据。
- 🤫 **隐蔽模式**：界面设计伪装成普通系统工具或仪表盘，拒绝社死。
- ⚡ **轻量高效**：极低的资源占用，适合后台常驻运行。
- 🛠 **简单配置**：通过 JSON 文件轻松管理你的自选股。

## 快速开始

### 环境要求

- Python 3.8+
- [Anaconda](https://www.anaconda.com/) 或 [Miniconda](https://docs.conda.io/en/latest/miniconda.html) (推荐)

### 安装步骤

1. 克隆项目仓库：
   ```bash
   git clone https://github.com/your-username/boss-is-talking-im-buying.git
   cd boss-is-talking-im-buying
   ```

2. 创建并激活虚拟环境：
   ```bash
   conda create -n stock python=3.10
   conda activate stock
   ```

3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用指南

### 一键运行

直接运行批处理文件即可：

```bash
run.bat
```

或者手动运行 Python 脚本：

```bash
python stock_monitor.py
```

### 配置自选股

编辑 `stock_config.json` 文件，将你关注的股票代码加入列表。

```json
{
  "stocks": [
    "600519",
    "000001",
    "002594"
  ]
}
```

## 免责声明

本项目仅供学习交流使用。投资有风险，摸鱼需谨慎，被炒鱿鱼概不负责。

## 许可证

MIT
