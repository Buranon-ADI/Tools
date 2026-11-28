#include <Wire.h>

// Device d (0..7) -> I2C 0x20 + d; A2/A1/A0 set by jumpers H6/H5/H3 (GND = 0)
const uint8_t MCP_BASE  = 0x20;
const uint8_t MCP_COUNT = 8;
const uint8_t PIN_RESET = 8;
// K17 connects DAC1 to sig_in_4; Q2 gate has a pull-up (R47), so K17 closes whenever D2 is not driven
const uint8_t PIN_K17   = 2;
const unsigned long PULSE_MAX_MS = 60000;

// IOCON.BANK = 0 register map
const uint8_t REG_IODIRA = 0x00;
const uint8_t REG_IOCON  = 0x0A;
const uint8_t REG_GPIOA  = 0x12;
const uint8_t REG_OLATA  = 0x14;

// Bit n of the 16-bit state = relay K(n+1); GPA = K1..K8, GPB = K9..K16.
// Row r, column c (1-based) -> K = (r-1)*4 + c. GPIO high -> ULN2803 sinks -> relay on.
uint16_t relayState[MCP_COUNT];
uint8_t  presentMask = 0;

bool isPresent(uint8_t dev) {
  return dev < MCP_COUNT && bitRead(presentMask, dev);
}

bool mcpProbe(uint8_t dev) {
  Wire.beginTransmission(MCP_BASE + dev);
  return Wire.endTransmission() == 0;
}

bool mcpWrite16(uint8_t dev, uint8_t reg, uint16_t value) {
  Wire.beginTransmission(MCP_BASE + dev);
  Wire.write(reg);
  Wire.write(value & 0xFF);
  Wire.write(value >> 8);
  return Wire.endTransmission() == 0;
}

bool mcpWrite8(uint8_t dev, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MCP_BASE + dev);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool mcpRead16(uint8_t dev, uint8_t reg, uint16_t &value) {
  Wire.beginTransmission(MCP_BASE + dev);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint8_t)(MCP_BASE + dev), (uint8_t)2) != 2) return false;
  uint8_t lo = Wire.read();
  uint8_t hi = Wire.read();
  value = ((uint16_t)hi << 8) | lo;
  return true;
}

// D8 only reaches the MCP23017 whose RESET# is wired to it
void mcpHardReset() {
  digitalWrite(PIN_RESET, LOW);
  delay(1);
  digitalWrite(PIN_RESET, HIGH);
  delay(1);
}

bool mcpInit(uint8_t dev) {
  // SEQOP = 0 (auto-increment A->B), BANK = 0
  if (!mcpWrite8(dev, REG_IOCON, 0x00)) return false;
  // Latch all-off before switching to outputs so no relay glitches on
  if (!mcpWrite16(dev, REG_OLATA, 0x0000)) return false;
  if (!mcpWrite16(dev, REG_IODIRA, 0x0000)) return false;
  relayState[dev] = 0;
  return true;
}

// Newly found devices are initialised (all off); devices already present keep their state
void scanBus(bool reinitAll) {
  Serial.println(F("  | Dev | Addr | Status   |"));
  Serial.println(F("  |-----|------|----------|"));
  for (uint8_t dev = 0; dev < MCP_COUNT; dev++) {
    bool was = bitRead(presentMask, dev);
    bool ok  = mcpProbe(dev);
    const __FlashStringHelper *status;
    if (!ok) {
      status = was ? F("LOST    ") : F("--      ");
    } else if (was && !reinitAll) {
      status = F("OK      ");
    } else {
      ok     = mcpInit(dev);
      status = ok ? F("INIT    ") : F("INIT ERR");
    }
    bitWrite(presentMask, dev, ok);

    char buf[24];
    snprintf(buf, sizeof(buf), "  | %u   | 0x%02X | ", dev, MCP_BASE + dev);
    Serial.print(buf);
    Serial.print(status);
    Serial.println(F(" |"));
  }
  if (presentMask == 0) Serial.println(F("ERR: no MCP23017 found"));
}

bool setRelays(uint8_t dev, uint16_t mask) {
  if (!mcpWrite16(dev, REG_OLATA, mask)) return false;
  relayState[dev] = mask;
  return true;
}

void printStatus(uint8_t dev) {
  uint16_t olat, gpio;
  if (!mcpRead16(dev, REG_OLATA, olat) || !mcpRead16(dev, REG_GPIOA, gpio)) {
    Serial.print(F("ERR: I2C read failed on dev "));
    Serial.println(dev);
    return;
  }
  char buf[48];
  snprintf(buf, sizeof(buf), "  Dev %u (0x%02X)  OLAT: %04X  GPIO: %04X", dev, MCP_BASE + dev, olat, gpio);
  Serial.println(buf);
  Serial.println(F("  | Row  | C1 | C2 | C3 | C4 |"));
  Serial.println(F("  |------|----|----|----|----|"));
  for (uint8_t r = 0; r < 4; r++) {
    Serial.print(F("  | ROW"));
    Serial.print(r + 1);
    Serial.print(F(" |"));
    for (uint8_t c = 0; c < 4; c++) {
      Serial.print(bitRead(gpio, r * 4 + c) ? F(" ON |") : F(" -- |"));
    }
    Serial.println();
  }
}

void printHelp() {
  Serial.println(F("Commands (d = device 0..7, default 0):"));
  Serial.println(F("  [d]A<p><l> -- set GPA<p> (0..7) to level <l> (0|1), e.g. 3A01 = dev 3 GPA0 high"));
  Serial.println(F("  [d]B<p><l> -- set GPB<p> (0..7) to level <l> (0|1), e.g. B30 = dev 0 GPB3 low"));
  Serial.println(F("  ON r c [d] -- close relay at row r, column c (1..4)"));
  Serial.println(F("  OFF r c [d]-- open relay at row r, column c"));
  Serial.println(F("  K n l [d]  -- set relay Kn (1..16) to l (0|1)"));
  Serial.println(F("  SET hhhh [d] -- write 16-bit hex mask (bit0 = K1)"));
  Serial.println(F("  PULSE n ms [d] -- close Kn (1..17) for ms (1..60000), then open"));
  Serial.println(F("  ALLOFF [d] -- open all relays (all devices + K17 if d omitted)"));
  Serial.println(F("  GET [d]    -- read back and print matrix (all devices if d omitted)"));
  Serial.println(F("  K17 0|1    -- open/close K17 (DAC1 -> sig_in_4)"));
  Serial.println(F("  SCAN       -- rescan 0x20..0x27, init newly found devices"));
  Serial.println(F("  INIT       -- hardware reset + rescan + reinit all devices"));
  Serial.println(F("  *IDN?      -- print firmware ID"));
}

void reportWrite(uint8_t dev, bool ok) {
  char buf[24];
  if (!ok) {
    snprintf(buf, sizeof(buf), "ERR: I2C write dev %u", dev);
  } else {
    snprintf(buf, sizeof(buf), "OK %u %04X", dev, relayState[dev]);
  }
  Serial.println(buf);
}

// Returns false (and prints error) if the device is absent
bool parseDev(const char *arg, uint8_t &dev) {
  dev = arg ? atoi(arg) : 0;
  if (!isPresent(dev)) {
    Serial.print(F("ERR: dev "));
    Serial.print(arg ? arg : "0");
    Serial.println(F(" not present (SCAN)"));
    return false;
  }
  return true;
}

void handleCommand(char *line) {
  char *cmd = strtok(line, " ");
  if (cmd == NULL) return;
  for (char *p = cmd; *p; p++) *p = toupper(*p);

  char *a1 = strtok(NULL, " ");
  char *a2 = strtok(NULL, " ");
  char *a3 = strtok(NULL, " ");

  // Pin command: optional device digit, then A|B, pin 0..7, level 0|1
  char *pin = cmd;
  char  devStr[2] = {'0', '\0'};
  if (strlen(cmd) == 4 && cmd[0] >= '0' && cmd[0] <= '7') {
    devStr[0] = cmd[0];
    pin       = cmd + 1;
  }
  if (strlen(pin) == 3 && (pin[0] == 'A' || pin[0] == 'B') &&
      pin[1] >= '0' && pin[1] <= '7' && (pin[2] == '0' || pin[2] == '1')) {
    uint8_t dev;
    if (!parseDev(devStr, dev)) return;
    uint8_t  bit  = (pin[0] == 'B' ? 8 : 0) + (pin[1] - '0');
    uint16_t mask = relayState[dev];
    bitWrite(mask, bit, pin[2] == '1');
    if (!setRelays(dev, mask)) {
      reportWrite(dev, false);
      return;
    }
    Serial.print(F("OK "));
    Serial.print(dev);
    Serial.print(F(" GP"));
    Serial.print(pin[0]);
    Serial.print(pin[1]);
    Serial.println(pin[2] == '1' ? F(" HIGH") : F(" LOW"));
  } else if (strcmp(cmd, "ON") == 0 || strcmp(cmd, "OFF") == 0) {
    int r = a1 ? atoi(a1) : 0;
    int c = a2 ? atoi(a2) : 0;
    if (r < 1 || r > 4 || c < 1 || c > 4) {
      Serial.println(F("ERR: row/col must be 1..4"));
      return;
    }
    uint8_t dev;
    if (!parseDev(a3, dev)) return;
    uint16_t mask = relayState[dev];
    bitWrite(mask, (r - 1) * 4 + (c - 1), cmd[1] == 'N');
    reportWrite(dev, setRelays(dev, mask));
  } else if (strcmp(cmd, "K") == 0) {
    int n = a1 ? atoi(a1) : 0;
    if (n < 1 || n > 16 || a2 == NULL) {
      Serial.println(F("ERR: K n 0|1 [d], n = 1..16"));
      return;
    }
    uint8_t dev;
    if (!parseDev(a3, dev)) return;
    uint16_t mask = relayState[dev];
    bitWrite(mask, n - 1, atoi(a2) != 0);
    reportWrite(dev, setRelays(dev, mask));
  } else if (strcmp(cmd, "SET") == 0) {
    if (a1 == NULL) {
      Serial.println(F("ERR: SET hhhh [d]"));
      return;
    }
    uint8_t dev;
    if (!parseDev(a2, dev)) return;
    reportWrite(dev, setRelays(dev, (uint16_t)strtoul(a1, NULL, 16)));
  } else if (strcmp(cmd, "PULSE") == 0) {
    int n = a1 ? atoi(a1) : 0;
    unsigned long ms = a2 ? strtoul(a2, NULL, 10) : 0;
    if (n < 1 || n > 17 || ms < 1 || ms > PULSE_MAX_MS) {
      Serial.println(F("ERR: PULSE n ms [d], n = 1..17, ms = 1..60000"));
      return;
    }
    char buf[32];
    // Blocking: serial input is buffered and handled after the pulse, so the reply marks the pulse end
    if (n == 17) {
      digitalWrite(PIN_K17, HIGH);
      delay(ms);
      digitalWrite(PIN_K17, LOW);
      snprintf(buf, sizeof(buf), "OK PULSE K17 %lu", ms);
      Serial.println(buf);
      Serial.println(F("OK K17 OPEN"));
      return;
    }
    uint8_t dev;
    if (!parseDev(a3, dev)) return;
    uint16_t bit = 1u << (n - 1);
    if (!setRelays(dev, relayState[dev] | bit)) {
      reportWrite(dev, false);
      return;
    }
    delay(ms);
    bool ok = setRelays(dev, relayState[dev] & ~bit);
    if (ok) {
      snprintf(buf, sizeof(buf), "OK PULSE %u K%d %lu", dev, n, ms);
      Serial.println(buf);
    }
    reportWrite(dev, ok);
  } else if (strcmp(cmd, "ALLOFF") == 0) {
    if (a1) {
      uint8_t dev;
      if (!parseDev(a1, dev)) return;
      reportWrite(dev, setRelays(dev, 0x0000));
    } else {
      for (uint8_t dev = 0; dev < MCP_COUNT; dev++) {
        if (isPresent(dev)) reportWrite(dev, setRelays(dev, 0x0000));
      }
      digitalWrite(PIN_K17, LOW);
      Serial.println(F("OK K17 OPEN"));
    }
  } else if (strcmp(cmd, "GET") == 0) {
    if (a1) {
      uint8_t dev;
      if (!parseDev(a1, dev)) return;
      printStatus(dev);
    } else {
      for (uint8_t dev = 0; dev < MCP_COUNT; dev++) {
        if (isPresent(dev)) printStatus(dev);
      }
      Serial.println(digitalRead(PIN_K17) ? F("  K17: CLOSED") : F("  K17: OPEN"));
    }
  } else if (strcmp(cmd, "K17") == 0) {
    if (a1 == NULL || (strcmp(a1, "0") != 0 && strcmp(a1, "1") != 0)) {
      Serial.println(F("ERR: K17 0|1"));
      return;
    }
    digitalWrite(PIN_K17, a1[0] == '1');
    Serial.println(a1[0] == '1' ? F("OK K17 CLOSED") : F("OK K17 OPEN"));
  } else if (strcmp(cmd, "SCAN") == 0) {
    scanBus(false);
  } else if (strcmp(cmd, "INIT") == 0) {
    mcpHardReset();
    scanBus(true);
  } else if (strcmp(cmd, "*IDN?") == 0) {
    Serial.println(F("relay_matrix_v1.0"));
  } else if (strcmp(cmd, "HELP") == 0 || strcmp(cmd, "?") == 0) {
    printHelp();
  } else {
    Serial.println(F("ERR: unknown command (HELP)"));
  }
}

void setup() {
  // Drive D2 low first to override the R47 pull-up and open K17 as early as possible
  digitalWrite(PIN_K17, LOW);
  pinMode(PIN_K17, OUTPUT);

  pinMode(PIN_RESET, OUTPUT);
  digitalWrite(PIN_RESET, HIGH);

  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);

  Serial.println(F("Relay Matrix 4x4 -- MCP23017"));
  mcpHardReset();
  scanBus(true);
  printHelp();
}

void loop() {
  static char line[32];
  static uint8_t len = 0;

  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (len > 0) {
        line[len] = '\0';
        handleCommand(line);
        len = 0;
      }
    } else if (len < sizeof(line) - 1) {
      line[len++] = ch;
    }
  }
}
