#!/usr/bin/env python3
"""Batch optimization runner - bypasses MCP 30s timeout by calling API directly."""
import requests, json, itertools, sys, time

API = 'http://localhost:8003'

CONFIGS = {
    'value_area': {
        'grids': {
            'lookback_periods': [12, 24, 36, 48],
            'value_area_percent': [0.65, 0.70, 0.75],
            'stop_atr_multiplier': [1.5, 2.0, 2.5],
        },
        'strategy': 'value_area',
        'symbol': 'CrudeOIL',
        'start': '2024-01-01',
        'end': '2024-12-31',
    },
    'mr_oil': {
        'grids': {
            'lookback': [10, 15, 20, 25, 30, 40],
            'std_threshold': [1.5, 2.0, 2.5, 3.0, 3.5],
        },
        'strategy': 'mean_reversion',
        'symbol': 'CrudeOIL',
        'start': '2024-01-01',
        'end': '2024-12-31',
    },
    'mr_oil_recent': {
        'grids': {
            'lookback': [15, 20, 25, 30, 40],
            'std_threshold': [2.0, 2.5, 3.0, 3.5],
        },
        'strategy': 'mean_reversion',
        'symbol': 'CrudeOIL',
        'start': '2024-06-01',
        'end': '2025-01-31',
    },
    'mr_msft': {
        'grids': {
            'lookback': [10, 15, 20, 25, 30],
            'std_threshold': [1.5, 2.0, 2.5, 3.0],
        },
        'strategy': 'mean_reversion',
        'symbol': 'MSFT',
        'start': '2024-01-01',
        'end': '2024-12-31',
    },
    'mr_tsla': {
        'grids': {
            'lookback': [10, 15, 20, 25, 30],
            'std_threshold': [1.5, 2.0, 2.5, 3.0],
        },
        'strategy': 'mean_reversion',
        'symbol': 'TSLA',
        'start': '2024-01-01',
        'end': '2024-12-31',
    },
}

def run_optimization(mode):
    cfg = CONFIGS[mode]
    keys = list(cfg['grids'].keys())
    combos = list(itertools.product(*[cfg['grids'][k] for k in keys]))
    results = []
    errors = 0
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  {mode}: {cfg['strategy']} on {cfg['symbol']} H1")
    print(f"  {cfg['start']} to {cfg['end']} | {len(combos)} combinations")
    print(f"{'='*60}")

    for i, vals in enumerate(combos):
        params = dict(zip(keys, vals))
        payload = {
            'symbol': cfg['symbol'],
            'timeframe': 'H1',
            'start_date': cfg['start'],
            'end_date': cfg['end'],
            'strategy': cfg['strategy'],
            'initial_capital': 3000,
            'strategy_params': params
        }
        try:
            r = requests.post(f'{API}/api/backtesting/vectorized/run', json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                m = data.get('metrics', data)
                results.append({
                    'params': params,
                    'return_pct': round(m.get('total_return_pct', 0), 3),
                    'sharpe': round(m.get('sharpe_ratio', 0), 3),
                    'trades': m.get('total_trades', 0),
                    'win_rate': round(m.get('win_rate', 0), 1),
                    'max_dd': round(m.get('max_drawdown_pct', 0), 2),
                    'pf': round(m.get('profit_factor', 0), 3),
                    'final_capital': round(m.get('final_capital', 0), 2),
                })
            else:
                errors += 1
        except Exception as e:
            errors += 1

    elapsed = time.time() - t0
    results.sort(key=lambda x: x.get('return_pct', -999), reverse=True)

    print(f"\n  Completed in {elapsed:.1f}s | {len(results)} results | {errors} errors")
    if results:
        print(f"\n  TOP 5:")
        for j, r in enumerate(results[:5]):
            print(f"    {j+1}. Return: {r['return_pct']:+.2f}% | Sharpe: {r['sharpe']:.2f} | "
                  f"Trades: {r['trades']} | WR: {r['win_rate']:.0f}% | "
                  f"DD: {r['max_dd']:.1f}% | PF: {r['pf']:.2f} | {r['params']}")

    return {
        'mode': mode,
        'strategy': cfg['strategy'],
        'symbol': cfg['symbol'],
        'period': f"{cfg['start']} to {cfg['end']}",
        'total_tested': len(combos),
        'elapsed_s': round(elapsed, 1),
        'errors': errors,
        'results': results,
    }


if __name__ == '__main__':
    modes = sys.argv[1:] if len(sys.argv) > 1 else list(CONFIGS.keys())

    all_results = {}
    for mode in modes:
        if mode not in CONFIGS:
            print(f"Unknown mode: {mode}. Available: {list(CONFIGS.keys())}")
            continue
        all_results[mode] = run_optimization(mode)

    outfile = '/tmp/batch_optimization_results.json'
    with open(outfile, 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  ALL RESULTS SAVED TO {outfile}")
    print(f"{'='*60}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  OPTIMIZATION SUMMARY")
    print(f"{'='*60}")
    for mode, data in all_results.items():
        best = data['results'][0] if data['results'] else None
        if best:
            print(f"\n  {mode} ({data['symbol']} {data['strategy']}):")
            print(f"    Best: {best['return_pct']:+.2f}% | Sharpe: {best['sharpe']:.2f} | "
                  f"Trades: {best['trades']} | WR: {best['win_rate']:.0f}% | Params: {best['params']}")
