# tick-rollup

**It turns a CSV of individual trades into OHLCV bars, one trading session at a time, using only the Python standard library.**

This is the honest version of a job that shows up in every market data pipeline: you get a
file of prints, you need bars, and the awkward parts are the session edges and the ticks
that arrive late. Those two things are the whole point of this repository. Everything else
is small enough to read in an afternoon.

## Quickstart

```sh
./run.sh test                                   # unit tests
./run.sh demo                                   # the shipped fixture, with the arithmetic
./run.sh ticks --out ticks.csv                  # 200k synthetic ticks, seed 7
./run.sh bar --input ticks.csv --out bars.csv   # 1 minute bars
./run.sh benchmark                              # throughput on a generated file
```

`run.sh` defaults to `/home/louis/.venvs/main/bin/python` and stops with a clear error if
that interpreter is missing. Point it at another Python 3.10+ with `PYTHON=python3 ./run.sh ...`.

`./run.sh ticks --rows` is an upper bound: the generator walks `--days` trading days
(default 3) and stops early once the row count is reached, so asking for more rows than
three days can hold gives you what three days hold. The benchmark prints the generated
count next to the requested one.

All three commands take `--interval 1m|5m|15m|30m|1h`, `--sessions 09:30-11:30,13:00-15:00`
and `--late strict|repair`.

### Input

```csv
timestamp,price,size,side
2026-03-02T09:30:00.000,100.10,200,B
```

Timestamps are ISO 8601, interpreted as exchange local time. Column order does not matter and
extra columns are ignored. `side` is optional. Bad rows stop the run with a line number rather
than being skipped quietly.

### Output

```csv
session,bar_start,bar_end,open,high,low,close,volume,turnover,trades,vwap,revised
09:30-11:30,2026-03-02T09:30:00,2026-03-02T09:31:00,100.100000,100.200000,100.050000,100.050000,600.000000,60085.000000,3,100.141667,no
```

Counters go to stderr so that stdout stays a clean CSV:

```
ticks_read=16 ticks_used=12 bars=9 dropped_out_of_session=2 dropped_late=2 repaired=0 bars_revised=0
```

## Cross-check

The fixture `examples/demo_ticks.csv` holds 16 ticks: two outside the session windows, two
deliberately out of order. Every number below came from `./run.sh demo` on this machine.

```
$ ./run.sh demo
fixture  examples/demo_ticks.csv  (16 ticks)
interval 1m
sessions 09:30-11:30, 13:00-15:00

== strict ==
ticks_read=16 ticks_used=12 bars=9 dropped_out_of_session=2 dropped_late=2 repaired=0 bars_revised=0

bar_start                 open       high        low      close     volume      turnover trades         vwap  revised
---------------------------------------------------------------------------------------------------------------------
2026-03-02T09:30:00   100.1000   100.2000   100.0500   100.0500      600.0      60085.00      3   100.141667  no
2026-03-02T09:31:00   100.3000   100.3000   100.2500   100.2500      500.0      50145.00      2   100.290000  no
2026-03-02T09:32:00   100.4000   100.4000   100.4000   100.4000      250.0      25100.00      1   100.400000  no
2026-03-02T09:34:00   100.3500   100.3500   100.3500   100.3500      150.0      15052.50      1   100.350000  no
2026-03-02T09:35:00   100.5000   100.5000   100.5000   100.5000      500.0      50250.00      1   100.500000  no
2026-03-02T13:00:00   100.7000   100.7000   100.7000   100.7000      200.0      20140.00      1   100.700000  no
2026-03-02T13:04:00   100.8000   100.8000   100.8000   100.8000      100.0      10080.00      1   100.800000  no
2026-03-02T13:05:00   100.6500   100.6500   100.6500   100.6500      300.0      30195.00      1   100.650000  no
2026-03-02T13:06:00   100.5500   100.5500   100.5500   100.5500      200.0      20110.00      1   100.550000  no

09:30 volume   = 200 + 300 + 100 = 600
09:30 turnover = 100.10*200 + 100.20*300 + 100.05*100 = 60085.00
09:30 vwap     = 60085.00 / 600 = 100.141667
09:30 ohlc     = open 100.10 high 100.20 low 100.05 close 100.05
09:31 volume   = 400 + 100 = 500
09:31 turnover = 100.30*400 + 100.25*100 = 50145.00
09:31 vwap     = 50145.00 / 500 = 100.290000
09:31 ohlc     = open 100.30 high 100.30 low 100.25 close 100.25

== repair ==
ticks_read=16 ticks_used=13 bars=9 dropped_out_of_session=2 dropped_late=1 repaired=1 bars_revised=1

bar_start                 open       high        low      close     volume      turnover trades         vwap  revised
---------------------------------------------------------------------------------------------------------------------
2026-03-02T09:30:00   100.1000   100.2000   100.0500   100.0500      600.0      60085.00      3   100.141667  no
2026-03-02T09:31:00   100.3000   100.3000   100.1500   100.2500      550.0      55152.50      3   100.277273  yes
2026-03-02T09:32:00   100.4000   100.4000   100.4000   100.4000      250.0      25100.00      1   100.400000  no
2026-03-02T09:34:00   100.3500   100.3500   100.3500   100.3500      150.0      15052.50      1   100.350000  no
2026-03-02T09:35:00   100.5000   100.5000   100.5000   100.5000      500.0      50250.00      1   100.500000  no
2026-03-02T13:00:00   100.7000   100.7000   100.7000   100.7000      200.0      20140.00      1   100.700000  no
2026-03-02T13:04:00   100.8000   100.8000   100.8000   100.8000      100.0      10080.00      1   100.800000  no
2026-03-02T13:05:00   100.6500   100.6500   100.6500   100.6500      300.0      30195.00      1   100.650000  no
2026-03-02T13:06:00   100.5500   100.5500   100.5500   100.5500      200.0      20110.00      1   100.550000  no

revised bars:
bar_start                 open       high        low      close     volume      turnover trades         vwap  revised
---------------------------------------------------------------------------------------------------------------------
2026-03-02T09:31:00   100.3000   100.3000   100.1500   100.2500      550.0      55152.50      3   100.277273  yes
```

What to look at:

- 09:30 is `200 + 300 + 100 = 600` shares and `60085 / 600 = 100.141667`. The tick at
  `09:30:59.999` is the close of that bar, the tick at `09:31:00.000` opens the next one.
- 09:33 never traded, so there is no row for it. Empty bars are not invented.
- 09:29:59 and 12:00:00 are outside the windows and counted as `dropped_out_of_session`.
- The tick at `09:31:20`, read after 09:34, is dropped in strict mode (`dropped_late=2`,
  the second one is the `09:31:25` tick at the end of the file) and folded into the 09:31
  bar in repair mode, which is why that bar is marked `yes` and carries 550 shares.
- In repair mode the 09:31 open stays 100.30 and the close stays 100.25, because open and
  close follow trade time, not the order the lines were read.

## Tests

```
$ ./run.sh test
----------------------------------------------------------------------
Ran 87 tests in 0.501s

OK
```

The suite covers bucket edges at 1m, 5m and 15m, the lunch gap, a file spanning two days,
strict versus repair on the same ticks, VWAP against hand arithmetic, zero size trades,
empty input, single tick input, header and row errors, generator determinism, the accounting
identity below, and all three CLI commands end to end.

## Benchmark

```
$ ./run.sh benchmark
file             /home/louis/.hermes/cache/scratch/rollup-bench-k1yugbq3/ticks.csv  (deleted after run)
rows             200000
file_mb          7.45
interval         1m
late_mode        strict
sessions         09:30-11:30,13:00-15:00
wall_seconds     0.769246
ticks_per_second 259995
bars             619
dropped_late     869
repaired         0
peak_rss_mb      17.9
generated_rows   200000  seed 7  days 3
```

Wall time is measured with `time.perf_counter()` around the roll-up loop only. File
generation is outside the timer. `peak_rss_mb` is `resource.getrusage(RUSAGE_SELF).ru_maxrss`
for the whole process, so it includes the interpreter. On this machine (CPython 3.14.4,
Linux) repeated runs of the same command landed between 0.77 s and 0.88 s, which is 230k to
260k ticks per second. Nothing here is multi-threaded; it is one loop over one file.

`./run.sh benchmark --late repair` on the same 200k rows reports `repaired=869
dropped_late=0` in about the same time, so keeping a session open for repairs costs little
on this workload.

## Design notes

**Session windows are data, not assumptions.** Default is `09:30-11:30,13:00-15:00`, parsed
from `--sessions`. Windows must be ordered, non overlapping and non touching; a bad spec is
an error, not a warning. Membership is inclusive at both ends, so the print stamped exactly
`11:30:00.000` still lands in the last bar instead of vanishing.

**The bar key is `(day, window_index, bucket_index)`.** The day is in the key so a file that
spans several days cannot mistake Tuesday 09:30 for a late tick from Monday, and the window
index is in the key so lunch is a hard boundary rather than a large gap in the same series.
Bucketing is `floor((t - window_start) / interval)`, with the last bucket clipped to the
window end. If a window is not a multiple of the interval you get one short trailing bar,
which is what the exchange would print.

**Bars close on a watermark.** A bar is final once a tick with a higher key has been seen.
In strict mode it is written out at that moment. In repair mode it is held until its session
ends, because a late tick can still arrive; sessions are flushed in time order, so output
stays sorted even when input is not.

**Late ticks are defined by key, not by clock drift.** A tick is late when its key is lower
than the highest key already seen. Strict drops it and increments `dropped_late`. Repair
folds it back into the bar, sets `revised`, and increments `repaired`. A tick older than the
session that has already been flushed cannot be repaired and is counted as `dropped_late`
instead of silently inventing a bar.

**Memory is bounded on purpose.** The reader streams line by line and never holds the file.
Strict mode keeps at most one open bar. Repair mode keeps the bars of the current session,
which is at most 120 bars at 1m, 24 at 5m and 8 at 15m with the default windows, whatever the
file size. For that reason peak RSS does not move with input length: it was 17.9 MB for
20,000 ticks and 17.9 MB for 232,747 ticks on the same machine.

**VWAP comes from the bar, not a second pass.** `turnover` is `sum(price * size)` and
`vwap = turnover / volume`. A bar with zero volume reports an empty `vwap` field rather than
a NaN or a zero.

**Accounting identity.** Every tick is one of three things:

```
ticks_read = ticks_used + dropped_out_of_session + dropped_late
```

For the benchmark run: `200000 = 198707 + 424 + 869`. There is a test for it.

## Limitations

- Prices and sizes are floats. Summing a few hundred thousand trades is fine at these
  magnitudes, but this is not a bookkeeping system; if you need exact money, use `Decimal`
  and expect to lose most of the throughput.
- Timestamps must be ISO 8601. Epoch seconds, `DD/MM/YYYY` and other local formats are not
  parsed, and the timezone offset is preserved in output but never used for bucketing. A
  file in UTC against sessions defined in local time will be bucketed wrongly.
- No bar filling. Minutes with no trades produce no row. Downstream code has to decide
  whether that means "no trades" or "missing feed".
- No deduplication. The same print twice counts twice.
- Repair stops at the session boundary. A tick for yesterday arriving after the session was
  flushed is dropped and counted, not written to a bar that has already been handed out.
- Bars are returned at session end in repair mode, which means a consumer cannot act on them
  intraday. Strict mode streams, repair mode batches.
- Single file, single thread, no partitioning by symbol. The input is assumed to be one
  instrument; a `symbol` column is ignored, so a mixed file would blend instruments.
- `benchmark` numbers are this machine's, generated data, warm cache. They are measured, not
  extrapolated, and not a promise about your disk.

## Layout

```
rollup/
  sessions.py   windows, interval parsing, bucketing
  bars.py       the bar record, CSV columns, VWAP
  reader.py     streaming CSV reader with line numbers in errors
  engine.py     watermark, late modes, counters
  synth.py      seeded synthetic tick generator
  cli.py        bar, benchmark, demo
tools/
  make_ticks.py CLI wrapper around rollup.synth
tests/          unittest suite, run with ./run.sh test
examples/
  demo_ticks.csv 16 ticks used by demo and by the cross-check above
run.sh          wrapper: test, ticks, or any rollup command
```

No third party packages, no network calls, no data from anywhere but the file you pass in.
