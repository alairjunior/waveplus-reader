# MIT License
#
# Copyright (c) 2018 Airthings AS
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# https://airthings.com

# ===============================
# Module import dependencies
# ===============================

from bluepy.btle import UUID, Peripheral, Scanner, DefaultDelegate
import argparse
import sys
import time
import struct
import tableprint

# ====================================
# Utility functions for WavePlus class
# ====================================

def parseSerialNumber(ManuDataHexStr):
    if (ManuDataHexStr == None or ManuDataHexStr == "None"):
        SN = "Unknown"
    else:
        ManuData = bytearray.fromhex(ManuDataHexStr)

        if (((ManuData[1] << 8) | ManuData[0]) == 0x0334):
            SN  =  ManuData[2]
            SN |= (ManuData[3] << 8)
            SN |= (ManuData[4] << 16)
            SN |= (ManuData[5] << 24)
        else:
            SN = "Unknown"
    return SN

# ===============================
# Class WavePlus
# ===============================

class WavePlus():
    def __init__(self, SerialNumber, hasAirQuality=False):
        self.periph        = None
        self.curr_val_char = None
        self.MacAddr       = None
        self.SN            = SerialNumber
        self.uuid          = "b42e2a68-ade7-11e4-89d3-123b93f75cba" if hasAirQuality else "b42e4dcc-ade7-11e4-89d3-123b93f75cba"
        self.numSensors    = 7 if hasAirQuality else 4

    def getNumSensors(self):
        return self.numSensors

    def connect(self):
        # Auto-discover device on first connection
        if (self.MacAddr is None):
            scanner     = Scanner().withDelegate(DefaultDelegate())
            searchCount = 0
            while self.MacAddr is None and searchCount < 50:
                devices      = scanner.scan(0.1) # 0.1 seconds scan period
                searchCount += 1
                for dev in devices:
                    ManuData = dev.getValueText(255)
                    SN = parseSerialNumber(ManuData)
                    if (SN == self.SN):
                        self.MacAddr = dev.addr # exits the while loop on next conditional check
                        break # exit for loop

            if (self.MacAddr is None):
                print("ERROR: Could not find device.")
                print("GUIDE: (1) Please verify the serial number.")
                print("       (2) Ensure that the device is advertising.")
                print("       (3) Retry connection.")
                sys.exit(1)

        # Connect to device
        try:
            if (self.periph is None):
                self.periph = Peripheral(self.MacAddr)

            if (self.curr_val_char is None):
                self.curr_val_char = self.periph.getCharacteristics(uuid=self.uuid)[0]
        except Exception as e:
           raise Exception("Failed to connect. Check if device is on and if you are close enough.")

    def read(self):
        if (self.curr_val_char is None):
            print("ERROR: Devices are not connected.")
            sys.exit(1)
        rawdata = self.curr_val_char.read()
        rawdata = struct.unpack('<BBBBHHHHHHHH', rawdata)
        sensors = Sensors(self.numSensors)
        sensors.set(rawdata)
        return sensors

    def disconnect(self):
        if self.periph is not None:
            self.periph.disconnect()
            self.periph = None
            self.curr_val_char = None

# ===================================
# Class Sensor and sensor definitions
# ===================================

class Sensors():
    HUMIDITY             = 0
    RADON_SHORT_TERM_AVG = 1
    RADON_LONG_TERM_AVG  = 2
    TEMPERATURE          = 3
    REL_ATM_PRESSURE     = 4
    CO2_LVL              = 5
    VOC_LVL              = 6
    def __init__(self, numberOfSensors):
        self.sensor_version = None
        self.numberOfSensors = numberOfSensors
        self.sensor_data    = [None]*numberOfSensors
        self.sensor_units   = ["%rH", "Bq/m3", "Bq/m3", "degC", "hPa", "ppm", "ppb"][:numberOfSensors]

    def set(self, rawData):
        self.sensor_version = rawData[0]
        if (self.sensor_version == 1):
            processor = {
                Sensors.HUMIDITY                 : rawData[1]/2.0,
                Sensors.RADON_SHORT_TERM_AVG     : self.conv2radon(rawData[4]),
                Sensors.RADON_LONG_TERM_AVG      : self.conv2radon(rawData[5]),
                Sensors.TEMPERATURE              : rawData[6]/100.0,
                Sensors.REL_ATM_PRESSURE         : rawData[7]/50.0,
                Sensors.CO2_LVL                  : rawData[8]*1.0,
                Sensors.VOC_LVL                  : rawData[9]*1.0
            }

            for sensor in range(self.numberOfSensors):
                self.sensor_data[sensor] = processor[sensor]

        else:
            print("ERROR: Unknown sensor version.\n")
            print("GUIDE: Contact Airthings for support.\n")
            sys.exit(1)

    def conv2radon(self, radon_raw):
        radon = "N/A" # Either invalid measurement, or not available
        if 0 <= radon_raw <= 16383:
            radon  = radon_raw
        return radon

    def getValue(self, sensor_index):
        return self.sensor_data[sensor_index]

    def getUnit(self, sensor_index):
        return self.sensor_units[sensor_index]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description ='Read values from Airthings Waveplus Sensor Devices')
    parser.add_argument('serial',
                        type = int,
                        help ='The Serial Number printed on the backplate of the device.')

    parser.add_argument('-t', '--period',
                        type = float,
                        help = 'The sample period, in seconds.',
                        default = 3 )

    parser.add_argument('-q', '--hasAirQuality',
                        help='Does the device has air quality sensors?',
                        action='store_true' )

    parser.add_argument('--plain',
                        help='Does not format the output for pretty printing.',
                        )


    args = parser.parse_args()

    try:
        #---- Initialize ----#
        waveplus = WavePlus(args.serial, args.hasAirQuality)

        if ( not args.plain ):
            print("\nPress ctrl+C to exit program\n")

        print("Device serial number: %s" %(args.serial))

        header = ['Humidity', 'Radon ST avg', 'Radon LT avg', 'Temperature', 'Pressure', 'CO2 level', 'VOC level'][:waveplus.getNumSensors()]

        if ( not args.plain ):
            print(tableprint.header(header, width=12))
        else:
            print(header)

        while True:
            waveplus.connect()

            # read values
            sensors = waveplus.read()

            numSensors = waveplus.getNumSensors()

            formater = {
                Sensors.HUMIDITY                : lambda: str(sensors.getValue(Sensors.HUMIDITY))             + " " + str(sensors.getUnit(Sensors.HUMIDITY)),
                Sensors.RADON_SHORT_TERM_AVG    : lambda: str(sensors.getValue(Sensors.RADON_SHORT_TERM_AVG)) + " " + str(sensors.getUnit(Sensors.RADON_SHORT_TERM_AVG)),
                Sensors.RADON_LONG_TERM_AVG     : lambda: str(sensors.getValue(Sensors.RADON_LONG_TERM_AVG))  + " " + str(sensors.getUnit(Sensors.RADON_LONG_TERM_AVG)),
                Sensors.TEMPERATURE             : lambda: str(sensors.getValue(Sensors.TEMPERATURE))          + " " + str(sensors.getUnit(Sensors.TEMPERATURE)),
                Sensors.REL_ATM_PRESSURE        : lambda: str(sensors.getValue(Sensors.REL_ATM_PRESSURE))     + " " + str(sensors.getUnit(Sensors.REL_ATM_PRESSURE)),
                Sensors.CO2_LVL                 : lambda: str(sensors.getValue(Sensors.CO2_LVL))              + " " + str(sensors.getUnit(Sensors.CO2_LVL)),
                Sensors.VOC_LVL                 : lambda: str(sensors.getValue(Sensors.VOC_LVL))              + " " + str(sensors.getUnit(Sensors.VOC_LVL))
            }
            data = [ formater[x]() for x in range(numSensors) ]
            if ( not args.plain ):
                print(tableprint.row(data, width=12))
            else:
                print(data)

            waveplus.disconnect()

            time.sleep(args.period)

    except Exception as e:
        print(str(e))
        print()

    finally:
        waveplus.disconnect()
