# DAQ973A + DAQM909A Summary

## Device Info

- **Instrument:** Keysight DAQ973A (next-gen replacement for 34972A)
- **Module:** DAQM909A — 4-channel 24-bit digitizer, inserted in slot 1
- **Data Sheet** https://docs.rs-online.com/eeec/A700000006654136.pdf
- **User Guide** https://www.mouser.com/pdfDocs/DAQ97-90000.pdf
- **Programming Guide** https://www.batronix.com/files/Keysight/DAQ/DAQ970A-973A-Programming.pdf

- **`*IDN?` returns `34972A`** — DAQ973A emulates 34972A identity for backward compatibility
  - Reference: https://www.keysight.com/th/en/assets/7018-06322/white-papers/5992-3306.pdf

---

## Acquisition Flow

```
ACQ3:VOLT  range,type,coupling,mode,samp_count,samp_rate,(@ch)   configure DC voltage
INIT3      (@ch)                                                  start acquisition
*OPC?                                                             wait for acquisition complete
FETCh3?    (@ch)                                                  fetch all raw samples (comma-separated)
FETCh3:STATistics?  record,first_pt,last_pt,(@ch)                fetch avg,std_dev,min,max
```

---

## Channel Config Parameters

| Field | SCPI Command | Options | Default | Notes |
|-------|-------------|---------|---------|-------|
| `range` | `SENS3:VOLT:DC:RANG` | 300MV, 1V, 3V, 18V | 1V | Use lowest range that covers signal |
| `input_type` | `INP3:TYPE` | DIFF, SEND, IEPE | DIFF | DIFF for shunt/floating; SEND for ground-referenced; IEPE for accelerometers |
| `coupling` | `INP3:COUP` | AC, DC | DC | AC removes DC offset |
| `mode` | `SENS3:FILT:MODE` | TIME, FREQ | TIME | TIME = Sinc5 filter; FREQ = wideband; FREQ max rate is 100 kSa/s |
| `samp_count` | `SAMP3:COUN` | 512 – 50,331,584 | 512 | More samples = better averaging but slower |
| `samp_rate` | `SAMP3:RATE` | 1562.5, 3125, 6250, 12500, 25000, 50000, 100000, 200000, 400000, 800000 (Sa/s) | 100000 | Changing rate affects all channels with the same filter mode on the module |
| `statistics` | `FETCh3:STATistics?` | record, first_pt, last_pt | record=1, first_pt=1, last_pt=256 | Returns avg, std_dev, min, max — post-processing on instrument side |

---

## Known Issues Fixed

| Error | Cause | Fix |
|-------|-------|-----|
| `-420 Query UNTERMINATED` / `-230 Data corrupt or stale` | `FETCh3?` sent before acquisition complete | Added `*OPC?` between `INIT3` and `FETCh3?` |
| `-222 Data out of range` | `ACQ3:VOLT` rejects `samp_count=1` despite docs claiming MIN=1 | Changed to `DEF` (instrument uses 512) |

---

## Notes

- `ACQ3:VOLT` is a compound command — sets all parameters at once; use individual commands (e.g. `SENS3:VOLT:DC:RANG`) to change one setting without affecting others
- `INP3:TYPE IEPE` is only available via `INP3:TYPE`, not via `ACQ3:VOLT`
- `SAMP3:RATE` change affects **all channels** with the same filter mode on the module
- `FETCh3:STATistics?` computes avg/std_dev/min/max on the instrument — preferred over fetching all raw samples and averaging in Python
