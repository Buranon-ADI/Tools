const int PINS[] = {2, 3, 4, 5, 6, 7, 8, 9};
const int NUM_PINS = 8;
const int ADDR_PINS[] = {14, 15};  // A0, A1
String cmd;
int boardAddr;

void setup() {
  for (int i = 0; i < NUM_PINS; i++) {
    digitalWrite(PINS[i], HIGH);
    pinMode(PINS[i], OUTPUT);
  }
  pinMode(ADDR_PINS[0], INPUT_PULLUP);
  pinMode(ADDR_PINS[1], INPUT_PULLUP);
  boardAddr = (digitalRead(ADDR_PINS[1]) << 1) | digitalRead(ADDR_PINS[0]);
  Serial.begin(9600);
}

void loop() {
  if (Serial.available()) {
    cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "*IDN?") {
      Serial.print("8Ch Relay Control,");
      Serial.println(boardAddr);
    } else if (cmd.length() == 4 && cmd.startsWith("D") && cmd.charAt(2) == '_') {
      int pin = cmd.charAt(1) - '0';
      char state = cmd.charAt(3);
      if (pin >= 2 && pin <= 9 && (state == 'L' || state == 'H')) {
        digitalWrite(pin, state == 'L' ? LOW : HIGH);
      } else {
        Serial.println("Unknown commands");
      }
    } else {
      Serial.println("Unknown commands");
    }
  }
}
