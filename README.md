# JoinMarket CoinJoin Analyzer

Analyze JoinMarket Bitcoin CoinJoin transactions. Using greedy pre-processing and Integer Linear Programming (ILP).

## Features

- **Deterministic preprocessing**: Greedy heuristic for unambiguous input-output matches
- **Symmetry-breaking ILP**: Eliminates permutation duplicates, finds all distinct solutions
- **Memory-safe**: 10GB limit enforcement
- **Interrupt handling**: Ctrl+C saves progress
- **Incremental saves**: Solutions written after each discovery
- **Production-ready**: Modular architecture, comprehensive tests, CLI interface

## Installation

```bash
pip install -e .
```

## Usage

### CLI

```bash
# Analyze a transaction
joinmarket-analyze 0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf

# Custom parameters
joinmarket-analyze <txid> --max-fee-rel 0.1 --max-solutions 500

# Help
joinmarket-analyze --help

# Output is automatically saved to solutions_<txid_prefix>.json
```

### Docker

```bash
# Run with a transaction ID
docker run --rm ghcr.io/m0wer/joinmarket_analyzer:master 0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf

# Run with memory limit (recommended)
docker run --rm -m 10g ghcr.io/m0wer/joinmarket_analyzer:master <txid> --max-solutions 500

# Using docker-compose
docker-compose run --rm joinmarket-analyzer <txid>
```

### Python API

```python
from joinmarket_analyzer import analyze_transaction

solutions = analyze_transaction(
    txid="0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf",
    max_fee_rel=0.05,
    max_solutions=1000
)

for solution in solutions:
    print(f"Taker: Participant {solution.taker_index + 1}")
    print(f"Maker fees: {solution.total_maker_fees:,} sats")
```

### Working Example

```bash
docker run --rm ghcr.io/m0wer/joinmarket_analyzer:master \
  0cb4870cf2dfa3877851088c673d163ae3c20ebcd6505c0be964d8fbcc856bbf \
  --max-fee-rel 0.001 --max-solutions 10
```

<details>
<summary>View Output</summary>

```
Taker: Participant 4 (pays 21,368 sats)
  💰 Participant 1 (maker)
    Inputs: [0]
    Outputs: Equal=6,357,366 sats, Change[2]=113,283,033 sats
    Fee receives: 458 sats
  💰 Participant 2 (maker)
    Inputs: [1]
    Outputs: Equal=6,357,366 sats, Change[6]=2,089,662,830 sats
    Fee receives: 413 sats
  💰 Participant 3 (maker)
    Inputs: [3]
    Outputs: Equal=6,357,366 sats, Change[19]=765,432,353 sats
    Fee receives: 623 sats
  🎯 Participant 4 (taker)
    Inputs: [4]
    Outputs: Equal=6,357,366 sats, No change output
    Fee pays: 21,368 sats
  💰 Participant 5 (maker)
    Inputs: [5]
    Outputs: Equal=6,357,366 sats, Change[11]=3,044,723 sats
    Fee receives: 5,153 sats
  💰 Participant 6 (maker)
    Inputs: [6]
    Outputs: Equal=6,357,366 sats, Change[3]=10,187,122 sats
    Fee receives: 559 sats
  💰 Participant 7 (maker)
    Inputs: [7]
    Outputs: Equal=6,357,366 sats, Change[8]=90,781,833 sats
    Fee receives: 636 sats
  💰 Participant 8 (maker)
    Inputs: [8]
    Outputs: Equal=6,357,366 sats, Change[12]=8,045,121 sats
    Fee receives: 973 sats
  💰 Participant 9 (maker)
    Inputs: [9]
    Outputs: Equal=6,357,366 sats, Change[7]=100,823,618 sats
    Fee receives: 687 sats
  💰 Participant 10 (maker)
    Inputs: [11]
    Outputs: Equal=6,357,366 sats, Change[20]=8,125,627 sats
    Fee receives: 191 sats
  💰 Participant 11 (maker)
    Inputs: [2, 10]
    Outputs: Equal=6,357,366 sats, Change[1]=87,861 sats
    Fee receives: 693 sats
Total maker fees collected: 10,386 sats
Network fee: 10,982 sats
```
</details>

## Algorithm

### Greedy Preprocessing

1. **Single-input matching** (iterative): Match inputs to change outputs where only one valid pairing exists
2. **Multi-input fallback**: Sequential assignment for remaining inputs
3. **Reduces search space**: Pre-assigns deterministic participants before ILP

### ILP Formulation

- **Variables**: Input assignments `x[i,p]`, change assignments `c[p,j]`, taker indicator `t[p]`
- **Symmetry breaking**: Orders participants by minimum input index
- **Partition cuts**: Excludes found solutions and all permutations
- **Constraints**: Balance equations, fee bounds, dust thresholds, maker fee non-positivity

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# E2E tests (requires network)
pytest tests/e2e/ -v

# All tests with coverage
pytest --cov=joinmarket_analyzer --cov-report=html
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Linting
pre-commit run --all-files
```

## Requirements

- Python 3.9+
- PuLP (CBC solver)
- Pydantic 2.x
- Loguru
- Requests

## Citation

If you use this tool in research, please cite:

```
@software{joinmarket_analyzer,
  title = {JoinMarket CoinJoin Analyzer},
  year = {2025},
  url = {https://github.com/m0wer/joinmarket-analyzer}
}
```

## Future Work & Research

This tool lays the groundwork for more advanced privacy research:

- **Entropy Evaluation**: Measure how "ambiguous" change outputs are. If multiple valid solutions exist, the Taker is harder to pinpoint.
- **Algorithm Design**: Evaluate and improve taker algorithms to intentionally create ambiguous change structures.
- **Market Statistics**: Analyze historical CoinJoins to gather statistics on fee limits used by takers and earnings by makers.

## Notes

- Assumes JoinMarket protocol structure (equal outputs, optional change)
- CBC solver timeout: 60s per iteration
- Uses `mempool.sgn.space` API for transaction data (requires network access)

## License

MIT License
