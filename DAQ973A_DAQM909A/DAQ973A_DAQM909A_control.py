import pyvisa
from dataclasses import dataclass

VISA_ADDRESS = "USB0::0x2A8D::0x8601::MY59011052::INSTR"
SLOT         = 1   # slot where DAQM909A is inserted (1-3)

# DAQM909A SCPI commands (ACQ3/INIT3/FETCh3 subsystem requires DAQM909A digitizer module)
# -----------------------------------------------------------------------------------------
# ACQ3:VOLT  range,type,coupling,mode,samp_count,samp_rate,(@ch)  configure DC voltage
# INIT3      (@ch)                                                 start acquisition
# *OPC?                                                            wait for acquisition complete
# FETCh3?    (@ch)                                                 fetch all raw samples
# FETCh3:STATistics?  record,first_pt,last_pt,(@ch)               fetch avg,std_dev,min,max
# -----------------------------------------------------------------------------------------
# Per-channel individual commands (alternative to ACQ3:VOLT compound command):
# SENS3:VOLT:DC:RANG  {300MV|1V|3V|18V|DEF}  (@ch)               set voltage range
# INP3:TYPE           {DIFF|SEND|IEPE}         (@ch)               set input type
# INP3:COUP           {AC|DC}                  (@ch)               set input coupling
# SENS3:FILT:MODE     {TIME|FREQ}              (@ch)               set ADC filter mode
# SAMP3:COUN          {512..50331584|DEF}      (@ch)               set sample count
# SAMP3:RATE          {1562.5..800000|DEF}     (@ch)               set sample rate


@dataclass
class ChannelConfig:
    # field         dedicated SCPI command                          options
    # -----------   --------------------------------------------    ----------------------------------
    range:      str = "DEF"  # SENS3:VOLT:DC:RANG  (@ch)          300MV | 1V | 3V | 18V | DEF
    input_type: str = "DEF"  # INP3:TYPE           (@ch)          DIFF | SEND | IEPE | DEF
    coupling:   str = "DEF"  # INP3:COUP           (@ch)          AC | DC | DEF
    mode:       str = "DEF"  # SENS3:FILT:MODE     (@ch)          TIME | FREQ | DEF
    samp_count: str = "DEF"  # SAMP3:COUN          (@ch)          512..50331584 | DEF (def=512)
    samp_rate:  str = "DEF"  # SAMP3:RATE          (@ch)          1562.5|3125|6250|12500|25000|50000|100000|200000|400000|800000 | DEF (def=100000)


CHANNEL_CONFIGS = {
    1: ChannelConfig(),
    2: ChannelConfig(),
    3: ChannelConfig(),
    4: ChannelConfig(),
}


def read_voltage_dc(daq: pyvisa.resources.Resource, slot: int, ch: int, cfg: ChannelConfig) -> float:
    channel_id = slot * 100 + ch
    samp_count = 512 if cfg.samp_count == "DEF" else int(cfg.samp_count)
    daq.write(f"ACQ3:VOLT {cfg.range},{cfg.input_type},{cfg.coupling},{cfg.mode},{cfg.samp_count},{cfg.samp_rate},(@{channel_id})")
    daq.write(f"INIT3 (@{channel_id})")
    daq.query("*OPC?")  # block until acquisition complete before fetching
    response = daq.query(f"FETCh3:STATistics? 1,1,{samp_count},(@{channel_id})")
    avg, *_ = [float(v) for v in response.strip().split(",")]
    return avg


def main():
    rm  = pyvisa.ResourceManager()
    daq = rm.open_resource(VISA_ADDRESS)
    daq.timeout = 10_000

    # DAQ973A emulates 34972A identity for backward compatibility — *IDN? returns "34972A"
    # https://www.keysight.com/th/en/assets/7018-06322/white-papers/5992-3306.pdf
    idn = daq.query("*IDN?").strip()
    manufacturer, model, serial, firmware = idn.split(",")
    print(f"  {'Manufacturer':<14}: {manufacturer}")
    print(f"  {'Model':<14}: {model}")
    print(f"  {'Serial':<14}: {serial}")
    print(f"  {'Firmware':<14}: {firmware}")

    for ch, cfg in CHANNEL_CONFIGS.items():
        voltage = read_voltage_dc(daq, SLOT, ch, cfg)
        print(f"  {'CH'+str(SLOT*100+ch):<14}: {voltage:.6f} V")

    daq.close()
    rm.close()


if __name__ == "__main__":
    main()
