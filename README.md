<div align="center">

# 🇳🇵 N U M A Bot — NEPSE AI Trading & Market Intelligence
### Powered by Kronos Foundation Model for Financial Markets

<p align="center">
  <a href="https://huggingface.co/NeoQuasar"><img src="https://img.shields.io/badge/🤗-Hugging_Face-yellow.svg" alt="Hugging Face"></a>
  <a href="http://localhost:8888"><img src="https://img.shields.io/badge/🚀-NEPSE_Dashboard-blue.svg" alt="Dashboard"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Hardware-Apple_Silicon_MPS%20%7C%20NVIDIA_CUDA-purple.svg" alt="Hardware">
</p>

> **NUMA Bot** (NEPSE Unified Market Analyst) is a state-of-the-art AI trading bot and real-time analytical workstation tailored for the **Nepal Stock Exchange (NEPSE)**, utilizing the **Kronos autoregressive K-line foundation model**.

</div>

---

## 📑 Table of Contents
- [✨ Key Features](#-key-features)
- [🏗️ System Architecture](#️-system-architecture)
- [📦 Model Zoo](#-model-zoo)
- [⚡ Quick Start](#-quick-start)
- [🖥️ Dashboard Walkthrough](#️-dashboard-walkthrough)
- [🇳🇵 NEPSE Market Engine](#-nepse-market-engine)
- [🔧 Fine-Tuning Kronos](#-fine-tuning-kronos)
- [📖 Citation & License](#-citation--license)

---

## ✨ Key Features

### 🧠 1. Kronos AI Autoregressive Forecasting
- **Foundation Model Architecture**: Transformer-based decoder with discrete multi-dimensional candlestick tokenization (OHLCV).
- **Sequential Prediction**: Generates multi-step future price trajectories, volatility envelopes, and breakout expectations.
- **Hardware Acceleration**: Automatic device dispatch on **Apple Silicon (MPS)**, **NVIDIA GPUs (CUDA)**, and high-performance multi-threaded CPU fallbacks.

### 📊 2. Multi-Panel Financial Charting Workstation
- **Dedicated Subcharts**: Independent, non-overlapping panels for **Volume**, **RSI (14)**, and **MACD (12, 26, 9)**.
- **Rich Technical Overlays**:
  - Exponential Moving Averages: EMA 9, EMA 21, EMA 50, EMA 200
  - Simple Moving Averages: SMA 20, SMA 50
  - Bollinger Bands (20, 2.0) with dynamic fill
  - Volume Weighted Average Price (VWAP)
  - Automatic Support & Resistance level detection
- **Responsive Layout**: Dark/Light mode theme persistence, persistent zoom/pan states, and synchronized multi-panel crosshairs.

### 🇳🇵 3. Native NEPSE Market Integration
- **Real-Time Calendar Awareness**: Handles Nepal Standard Time (**NPT, UTC+05:45**) and current **Monday–Friday** (11:00 AM – 3:00 PM) trading hours.
- **250+ Listed Securities**: Pre-categorized sectors across Commercial Banks, Development Banks, Hydropower, Finance, Life/Non-Life Insurance, Microfinance, and Manufacturing.
- **Multi-Source Ingestion**: Live fallback chains with disk and memory caching across public market feeds (Sharesansar, TMS client integration, and local historical databases).

### 📡 4. Real-Time Market Scanner & Trading Engine
- **Automated Screener**: Scans the entire NEPSE universe for bullish/bearish setups, momentum breakouts, and indicator confluences.
- **Signal Confluence Matrix**: Combines Kronos foundation model probabilities with classical technical signals to calculate confidence scores.
- **Virtual Portfolio Tracker**: Simulated order execution, stop-loss / take-profit calculations, unrealized P&L monitoring, and position sizing.

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        N U M A Dashboard (UI)                          │
│     Plotly Multi-Panel Charts • Live Scanner • Virtual Portfolio       │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ HTTP / REST APIs
┌───────────────────────────────────┴────────────────────────────────────┐
│                   Flask / Waitress WSGI Web Server                     │
│               nepse_bot/app.py  (Port 8888, 8 Threads)                 │
└───────────────┬───────────────────┬───────────────────┬────────────────┘
                │                   │                   │
   ┌────────────▼──────────┐ ┌──────▼──────────┐ ┌──────▼───────────┐
   │ Kronos Signal Engine  │ │  NEPSE Data Feed│ │  TMS & Portfolio │
   │ (Predictor / Model)   │ │  (nepse_data.py)│ │  (tms_client.py) │
   └────────────┬──────────┘ └──────┬──────────┘ └──────┬───────────┘
                │                   │                   │
   ┌────────────▼──────────┐ ┌──────▼──────────┐ ┌──────▼───────────┐
   │ HuggingFace Hub / MPS │ │ Live APIs & CSV │ │ SQLite / MySQL DB│
   │ Kronos-base / small   │ │ Sharesansar/NOTS│ │ db_manager.py    │
   └───────────────────────┘ └─────────────────┘ └──────────────────┘
```

---

## 📦 Model Zoo

| Model Name | Parameters | Tokenizer | Context Window | Best Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Kronos-base** | **102.3M** | `Kronos-Tokenizer-base` | 512 | Highest prediction accuracy & trajectory analysis |
| **Kronos-small** | **24.7M** | `Kronos-Tokenizer-base` | 512 | Fast inference, balanced CPU/GPU performance |
| **Kronos-mini** | **4.1M** | `Kronos-Tokenizer-2k` | 2048 | Lightweight, extended long-context forecasting |

All models download automatically from Hugging Face on demand:
- [`NeoQuasar/Kronos-base`](https://huggingface.co/NeoQuasar/Kronos-base)
- [`NeoQuasar/Kronos-small`](https://huggingface.co/NeoQuasar/Kronos-small)
- [`NeoQuasar/Kronos-mini`](https://huggingface.co/NeoQuasar/Kronos-mini)

---

## ⚡ Quick Start

### 1. Environment Setup

Clone the repository and install required dependencies:

```bash
git clone https://github.com/shikhartech/Kronos.git
cd Kronos

# Create and activate virtual environment (Python 3.10+)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r nepse_bot/requirements.txt
```

### 2. Launching NUMA Bot Dashboard

Start the high-performance dashboard directly via Python:

```bash
python nepse_bot/run.py
```

*Or alternatively using the background daemon script:*
```bash
./start.sh
```

Open your browser and navigate to:
```
http://localhost:8888
```

To gracefully terminate the server:
```bash
./stop.sh
```

---

## 🖥️ Dashboard Walkthrough

```
┌────────────────────────────────────────────────────────────────────────┐
│ 🇳🇵 N U M A Bot   [🟢 MARKET OPEN]  [12:30:00 NPT]   [☀️ Light/Dark]   │
├────────────────────────────────────────────────────────────────────────┤
│ [✅ Kronos-base (102.3M) loaded on MPS]  [Model: Kronos-base ▼] [Load] │
├────────────────────────────────────────────────────────────────────────┤
│ 🔍 Search: NABIL     [📊 Daily / Swing] [⚡ Intraday]   [🧠 Predict]    │
├────────────────────────────────────────────────────────────────────────┤
│ 🕯️ CANDLESTICK PRICE CHART (NPR 480 – 550)                             │
│   ── EMA 9/21/50/200 ── VWAP ── Bollinger Bands ── Support/Resistance │
├────────────────────────────────────────────────────────────────────────┤
│ 📊 VOLUME SUBCHART (Shares traded)                                     │
├────────────────────────────────────────────────────────────────────────┤
│ 📈 RSI 14 SUBCHART (Overbought: 70 | Oversold: 30)                     │
├────────────────────────────────────────────────────────────────────────┤
│ 📊 MACD SUBCHART (MACD Line, Signal Line, Histogram)                   │
├────────────────────────────────────────────────────────────────────────┤
│ 🧠 AI Forecast Analysis • Confluence Breakdown • Trading Checklist    │
└────────────────────────────────────────────────────────────────────────┘
```

### Configuration & Controls
- **Model Selector**: Switch between `Kronos-base`, `Kronos-small`, and `Kronos-mini`. Your selection automatically persists across browser refreshes.
- **Subcharts Toolbar**: Toggle Volume, RSI, and MACD on and off without affecting the main price candle scale.
- **Stock Search**: Search through all 250+ NEPSE tickers with auto-complete.

---

## 🇳🇵 NEPSE Market Engine

The `nepse_bot/nepse_data.py` module manages all market data processing:
- **Trading Schedule**: Automatically tracks Monday through Friday trading (11:00 AM – 3:00 PM NPT).
- **Timezone Standardization**: Enforces `UTC+05:45` regardless of host OS timezone settings.
- **Intraday & Swing Series**: Computes 5-minute intraday intervals and multi-year daily OHLCV series.
- **Indicator Engine** (`nepse_bot/indicators.py`): Pure NumPy/Pandas vector calculations for MACD, RSI, Supertrend, Stochastic, and ATR.

---

## 🔧 Fine-Tuning Kronos

To fine-tune Kronos on your custom financial dataset or custom exchange data:

1. **Configure Parameters**: Adjust paths and hyperparameters in `finetune/config.py`.
2. **Preprocess Data**:
   ```bash
   python finetune/qlib_data_preprocess.py
   ```
3. **Train Tokenizer & Predictor**:
   ```bash
   torchrun --standalone --nproc_per_node=2 finetune/train_tokenizer.py
   torchrun --standalone --nproc_per_node=2 finetune/train_predictor.py
   ```
4. **Evaluate & Backtest**:
   ```bash
   python finetune/qlib_test.py --device cuda:0
   ```

---

## 📖 Citation & License

If you use Kronos or NUMA Bot in your research or project:

```bibtex
@misc{shi2025kronos,
      title={Kronos: A Foundation Model for the Language of Financial Markets}, 
      author={Yu Shi and Zongliang Fu and Shuo Chen and Bohan Zhao and Wei Xu and Changshui Zhang and Jian Li},
      year={2025},
      eprint={2508.02739},
      archivePrefix={arXiv},
      primaryClass={q-fin.ST},
      url={https://arxiv.org/abs/2508.02739}
}
```

This project is licensed under the [MIT License](./LICENSE).

---

<div align="center">
  <sub>Built with ❤️ for quantitative traders and the Nepal Stock Exchange community.</sub>
</div>
