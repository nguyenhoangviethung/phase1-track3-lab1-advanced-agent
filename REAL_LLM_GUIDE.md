# Real LLM Integration Guide

## Status
✅ **Real OpenAI API Integration Complete**
✅ **Tested with gpt-4o-mini**
✅ **Auto-loads .env for API key**

## Setup

1. **Add API Key to .env**
```bash
# Create or update .env file in project root
OPENAI_API_KEY=sk-proj-...
```

2. **Install Required Packages**
```bash
pip install openai tiktoken
```

3. **Verify Setup**
```bash
python -c "from openai import OpenAI; print('✅ OpenAI ready')"
```

## Running Benchmarks

### Quick Test (10 samples, gpt-4o-mini - ~$0.05)
```bash
export $(grep -v '^#' .env | xargs)
python run_with_real_llm.py --limit-examples 10 --llm-model gpt-4o-mini
```

### Medium Run (50 samples - ~$0.25)
```bash
python run_with_real_llm.py --limit-examples 50 --llm-model gpt-4o-mini
```

### Full Benchmark (100 samples - ~$0.50)
```bash
python run_with_real_llm.py --limit-examples 100 --llm-model gpt-4o-mini
```

### Using More Capable Model (Slower, More Expensive)
```bash
python run_with_real_llm.py --limit-examples 50 --llm-model gpt-4-turbo
```

## Available Models

| Model | Speed | Cost | Quality |
|-------|-------|------|---------|
| gpt-4o-mini | ⚡ Fast | 💰 Cheap | Good |
| gpt-4-turbo | ⚠️ Medium | 💵 Moderate | Better |
| gpt-4o | ⚠️ Medium | 💵 Moderate | Best |

## Real LLM Results (gpt-4o-mini)

### Test Run (10 Samples)
```
ReAct Agent:
  - EM: 80%
  - Avg Attempts: 1.0
  - Avg Tokens: 614.9
  - Avg Latency: 2781.9ms (2.8s)

Reflexion Agent:
  - EM: 80%
  - Avg Attempts: 1.5
  - Avg Tokens: 1128.7
  - Avg Latency: 4720.8ms (4.7s)
  
Improvement: No accuracy gain but 50% more attempts for robustness
```

## Output Files

Results are saved to `outputs/reflexion_run_real/`:
- `report.json` - Complete metrics in JSON format
- `report.md` - Formatted markdown report
- `react_runs.jsonl` - Individual ReAct run records
- `reflexion_runs.jsonl` - Individual Reflexion run records

## Token Counting

Accurate token counting is done via tiktoken:
- Tokens are counted for both input and output using GPT-4 tokenizer
- Falls back to character-based estimation if tiktoken unavailable
- Token counts are included in all metrics

## Error Handling

The system gracefully handles API errors:
- Failed API calls log error and skip that example
- Partial results are saved even if some examples fail
- Detailed error messages help diagnose issues

## Cost Estimation

Approximate cost for gpt-4o-mini (as of April 2026):
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens

For 100 samples (typically 500-1000 tokens per sample * 2 agents):
- ~$0.50-1.00 total cost

## Next Steps

1. Run mock mode for validation (free):
   ```bash
   python run_benchmark.py --use-mock --limit-examples 100
   ```

2. Run real LLM with small sample (cheap test):
   ```bash
   python run_with_real_llm.py --limit-examples 10
   ```

3. Scale up to full benchmark when confident:
   ```bash
   python run_with_real_llm.py --limit-examples 100
   python autograde.py --report-path outputs/reflexion_run_real/report.json
   ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `No module named 'openai'` | Run `pip install openai` |
| `OPENAI_API_KEY not found` | Add to `.env` file |
| `Invalid API key` | Check key is correct in `.env` |
| `Rate limit exceeded` | Reduce examples or wait |
| `401 Unauthorized` | API key expired or invalid |

## Features

✅ Real-time token counting with tiktoken
✅ Accurate latency measurement
✅ Structured error handling
✅ Automatic .env loading
✅ Progress tracking with rich library
✅ Comprehensive JSON output
✅ Compatible with original autograde.py
