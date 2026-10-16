# Free LLM API Tracker

Self-updating tracker for free-tier LLM API access.

## Setup

```bash
cd tracker-core
pip install -e ".[dev]"

cd ../free-api-tracker
python main.py check    # Run initial check
python main.py report   # Generate HTML report
python main.py list     # List all providers
```

## Structure

```
free-api-tracker/
├── main.py              # Main entry point
├── data/                # Provider storage (created on first run)
├── .cache/              # Content cache (created on first run)
└── reports/             # Generated HTML reports
```

## Usage

```bash
# Check providers for updates
python main.py check

# Generate HTML report
python main.py report

# List all providers
python main.py list

# Mark provider as verified
python main.py verify --name "Google AI Studio"

# Use lain theme
python main.py report --theme lain
```

## Seed Providers

13 providers pre-configured:
- **Western**: Google AI Studio, OpenRouter, NVIDIA NIM, Mistral, Groq, Cerebras, Together AI
- **Chinese**: DeepSeek, Alibaba Qwen, Zhipu AI, Moonshot AI, MiniMax, 01.AI
