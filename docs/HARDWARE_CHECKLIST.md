# Physical Hardware Verification Checklist
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Target Hardware**: ESP8266 (NodeMCU v2/v3 ESP-12E) + 4-Channel Optocoupled Relay Board + PIR + LDR + DHT11  

> [!CAUTION]
> **MAINS VOLTAGE SAFETY WARNING (220V–240V AC)**  
> Never connect mains wiring to open prototype breadboards or exposed modules. Mains wiring must only be terminated in a certified electrical enclosure by qualified technical personnel. All initial verification must be performed using low-voltage DC bench indicators (LEDs or multimeter) before connecting physical appliances.

The software development agent cannot physically touch or inspect the hardware. The human operator **must** verify and sign off on each checklist item below before connecting real electrical loads.

---

## 1. Electrical Isolation & Physical Enclosure Checklist
- [ ] **Optocoupler Isolation**: Confirm the 4-channel relay module has optocoupler isolation (e.g., PC817). Verify the `JD-VCC` jumper is set appropriately: if powering relay coils from an external 5V supply, remove the `VCC-JDVCC` jumper to ensure complete galvanic isolation from the ESP8266 3.3V logic.
- [ ] **Contact Load Ratings**: Inspect relay contact ratings stamped on the relay cases (typically Songle `SRD-05VDC-SL-C`: 10A 250VAC resistive).
  - [ ] `light_01` load rating verified ($\le$ 200W).
  - [ ] `fan_01` ceiling fan rating verified ($\le$ 150W inductive; verify snubber / RC circuit across contacts).
  - [ ] `ac_01` verified **DISCONNECTED** from direct relay contacts. (A standard 1.5-ton AC draws 8A–12A running, and up to 35A–45A locked-rotor inductive surge. Switching direct mains through a 10A PCB relay is a serious fire hazard).
  - [ ] `pc_01` verified that no abrupt mains cutoff can destroy operator workstations.
- [ ] **Protective Grounding**: Confirm the metallic chassis/enclosure has a certified earth-ground connection bonded to the building mains ground rod.
- [ ] **Fused Overcurrent Protection**: Confirm each relay output channel is protected by an appropriately rated fast-blow fuse or circuit breaker.

---

## 2. Power Supply & Grounding Integrity Checklist
- [ ] **ESP8266 3.3V Power Rail**: ESP8266 Wi-Fi transmit bursts draw up to 250mA–350mA peak currents. Confirm the 3.3V regulator supplies at least 500mA without voltage drops below 3.0V (a brownout will cause reboot loops).
- [ ] **Relay Coil 5V Supply**: Ensure relay coils are driven from a dedicated 5V 1A+ DC power adapter and NOT back-powered from the ESP8266 3.3V pin.
- [ ] **Common Grounding**: Confirm GND of the ESP8266 and the 5V power supply are tied together if not using optocoupled JD-VCC isolation.

---

## 3. Microcontroller Pin Mapping & Boot State Checklist

The prototype sketch maps the following pins. Verify each pin on the physical board:

| Appliance / Sensor | ESP8266 Pin | NodeMCU Pin | Boot Behavior & Electrical Risk | Physical Verification Status |
|---|:---:|:---:|---|:---:|
| **PIR Motion Sensor** | GPIO14 | `D5` | Safe standard GPIO. Input. Confirm PIR output is 3.3V logic (some 5V PIRs output 3.3V logic; verify with DMM before connecting). | [ ] Pending |
| **LDR Sensor** | ADC0 | `A0` | Max 1.0V internal (NodeMCU has an on-board 220k/100k voltage divider supporting up to 3.3V). Verify divider resistance. | [ ] Pending |
| **DHT11 Data** | GPIO0 | `D3` | **CRITICAL BOOT PIN**: GPIO0 must be pulled HIGH at boot for normal execution. If DHT11 pulls GPIO0 LOW during power-on, the chip enters UART bootloader mode and hangs. Verify pull-up resistor. | [ ] Pending |
| **Relay Light (`light_01`)** | GPIO16 | `D0` | Deep-sleep wake pin. Has no internal pull-up resistor. Verify boot state does not float or chatter. | [ ] Pending |
| **Relay Fan (`fan_01`)** | GPIO12 | `D6` | Safe standard GPIO. Active-LOW. | [ ] Pending |
| **Relay PC (`pc_01`)** | GPIO13 | `D7` | Safe standard GPIO. Active-LOW. | [ ] Pending |
| **Relay AC (`ac_01`)** | GPIO15 | `D8` | **CRITICAL BOOT PIN**: GPIO15 must be pulled LOW at boot. If an active-LOW relay module with pull-up holds GPIO15 HIGH, the chip will fail to boot from flash. | [ ] Pending |
| **I2C LCD SDA** | GPIO4 | `D2` | Standard I2C bus. Needs 4.7kΩ pull-up to 3.3V. | [ ] Pending |
| **I2C LCD SCL** | GPIO5 | `D1` | Standard I2C bus. Needs 4.7kΩ pull-up to 3.3V. | [ ] Pending |

---

## 4. Relay Boot State & Chatter Verification (Bench Test)
- [ ] **Power-On Reset Test**: Power off the entire setup. Power on the ESP8266 with relay module attached (with loads disconnected, listening to relay clicks).
  - [ ] Confirm **NO** relay clicks or toggles occur while the ESP8266 is booting and connecting to Wi-Fi.
  - [ ] If relays click momentarily on boot, invert logic or reassign to safe GPIO pins (e.g. GPIO4, GPIO5, GPIO12, GPIO14) to prevent brief load energization during brownouts.
- [ ] **Active-Level Confirmation**:
  - [ ] Active-LOW confirmed: Driving GPIO `LOW` closes relay contact (NO $\to$ COM). Driving GPIO `HIGH` opens contact.

---

## 5. Sensor Calibration Verification (Room Conditions)
- [ ] **PIR Sensitivity & Retrigger Adjustment**:
  - [ ] Adjust the physical time-delay trimpot on the HC-SR501 module to its minimum (~3 seconds).
  - [ ] Set retrigger jumper to 'H' (repeatable trigger mode) so continuous motion maintains a continuous HIGH signal.
  - [ ] Walk test: verify LED indicator illuminates on motion across target office zones.
- [ ] **LDR Ambient Light Calibration**:
  - [ ] Measure raw ADC reading under pitch-black darkness (cover sensor): Record value: `________`
  - [ ] Measure raw ADC reading under normal daytime office illumination: Record value: `________`
  - [ ] Measure raw ADC reading with artificial room lights fully ON: Record value: `________`
  - [ ] Enter confirmed calibration values into `server/app/config.py` and activate `calibration_flag`.

---

## Verification Sign-Off
- Physical Verification Performed By: __________________________
- Date of Inspection: __________________________
- Authorization for Mains Connection: [ ] GRANTED  [ ] DENIED

