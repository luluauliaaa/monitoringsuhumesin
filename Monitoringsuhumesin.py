import paho.mqtt.client as mqtt
import serial
import time
import datetime as dt
import numpy as np
import cv2
import max6675
import RPi.GPIO as GPIO

# Input pin
sck1 = 11
cs1 = 13
so1 = 15
sck2 = 16
cs2 = 18
so2 = 22
sck3 = 29
cs3 = 31
so3 = 37
sck4 = 19
cs4 = 21
so4 = 23

# Set pin untuk setiap sensor
GPIO.setmode(GPIO.BOARD)
max6675.set_pin(cs1, sck1, so1, 1, 1)
max6675.set_pin(cs2, sck2, so2, 1, 2)
max6675.set_pin(cs3, sck3, so3, 1, 3)
max6675.set_pin(cs4, sck4, so4, 1, 4)

# Deklarasikan broker MQTT
broker_address = "192.168.0.5"
broker_port = 1883

# Deklarasikan client ID
client_id = "python-client"

# Buat client MQTT
client = mqtt.Client(client_id)

# Hubungkan ke broker MQTT
client.connect(broker_address, broker_port)

# Mulai loop MQTT
client.loop_start()

# Fungsi untuk mendapatkan suhu dari MCU (derajat Celsius x 100)
def get_temp_array(d):
    # Mendapatkan suhu ambien
    T_a = (int(d[1540]) + int(d[1541])*256)/100
    # Mendapatkan array mentah suhu piksel
    raw_data = d[4:1540]
    T_array = np.frombuffer(raw_data, dtype=np.int16)
    return T_a, T_array

# Fungsi untuk mengubah suhu ke piksel pada gambar
def td_to_image(f):
    norm = np.uint8((f/100 - Tmin)*255/(Tmax-Tmin))
    norm.shape = (24, 32)
    return norm

########################### Siklus Utama #################################
# Rentang peta warna
Tmax = 45
Tmin = 20

print('Configuring Serial port')
ser = serial.Serial('/dev/serial0')
ser.baudrate = 115200

# Set frekuensi modul ke 4 Hz
ser.write(serial.to_bytes([0xA5, 0x25, 0x01, 0xDC]))
time.sleep(0.1)

# Memulai pengumpulan data otomatis
ser.write(serial.to_bytes([0xA5, 0x35, 0x02, 0xDC]))
t0 = time.time()

try:
    while True:
        loop_start_time = time.time()
        
        # Menunggu frame data
        data = ser.read(1544)

        # Data sudah siap, mari kita proses!
        Ta, temp_array = get_temp_array(data)
        ta_img = td_to_image(temp_array)
        
        # Membaca suhu dari MAX6675
        temp1 = max6675.read_temp(cs1, sck1, so1, 1, 1)
        temp2 = max6675.read_temp(cs2, sck2, so2, 1, 2)
        temp3 = max6675.read_temp(cs3, sck3, so3, 1, 3)
        temp4 = max6675.read_temp(cs4, sck4, so4, 1, 4)
        # Hasil kalibrasi termokopel
        suhu1 = 1.3378 * temp1 - 12.619 
        suhu2 = 1.0781 * temp2 - 3.8046              
        suhu3 = 1.045 * temp3 - 2.7747
        suhu4 = 1.169 * temp4 - 6.8894

        # Pemrosesan gambar MLX90640
        img = cv2.applyColorMap(ta_img, cv2.COLORMAP_JET)
        img = cv2.resize(img, (480, 240), interpolation=cv2.INTER_CUBIC)
        img = cv2.flip(img, 1)
        suhumin = temp_array.min()/100 - 1.5
        suhumax = temp_array.max()/100 - 1.5
        suhumaxfinal = 0.999 * suhumax - 1.6736  # Persamaan setelah dikalibrasi
        if suhumaxfinal > 200:
            print(f"Ignored Tmax value: {suhumaxfinal}")
            suhumaxfinal = None
        if suhu1 < 25:
            print(f"Ignored suhu1 value: {suhu1}")
            suhu1 = None
        if suhu2 < 25:
            print(f"Ignored suhu2 value: {suhu2}")
            suhu2 = None
        if suhu3 < 25:
            print(f"Ignored suhu3 value: {suhu3}")
            suhu3 = None
        if suhu4 < 25:
            print(f"Ignored suhu4 value: {suhu4}")
            suhu4 = None
            
        text = 'Tmin = {:+.1f} Tmax = {:+.1f} FPS = {:.2f}'.format(suhumin,suhumaxfinal,1/(time.time() - t0))
        cv2.putText(img, text, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        
        # Tampilkan suhu dari MAX6675
        cv2.putText(img, "Termokopel 1: {:.2f} C".format(suhu1), (5, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        cv2.putText(img, "Termokopel 2: {:.2f} C".format(suhu2), (5, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        cv2.putText(img, "Termokopel 3: {:.2f} C".format(suhu3), (5, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        cv2.putText(img, "Termokopel 4: {:.2f} C".format(suhu4), (5, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
       
        # Menampilkan cv2
        cv2.imshow('Output', img)

        # Jika 's' ditekan - simpan gambar
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            fname = 'pic_' + dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + '.jpg'
            cv2.imwrite(fname, img)
            print('Saving image ', fname)

        # Publikasikan pesan ke topik MQTT
        # MLX90640
        message1 = "{{\"suhu minimal\": {:.1f}}}".format(suhumin)
        message2 = "{{\"suhu maksimal\": {:.1f}}}".format(suhumaxfinal)
        # MAX6675
        message3 = "{{\"suhu termokopel 1\": {:.1f}}}".format(suhu1)
        message4 = "{{\"suhu termokopel 2\": {:.1f}}}".format(suhu2)
        message5 = "{{\"suhu termokopel 3\": {:.1f}}}".format(suhu3)
        message6 = "{{\"suhu termokopel 4\": {:.1f}}}".format(suhu4)
        
        # MLX90640
        client.publish("suhu/Tmin", message1)
        client.publish("suhu/Tfixmax", message2)
        # MAX6675
        client.publish("suhu/suhu1", message3)
        client.publish("suhu/suhu2", message4)
        client.publish("suhu/suhu3", message5)
        client.publish("suhu/suhu4", message6)
        time.sleep(0.1)
        t0 = time.time()

        # Handle window close event
        if key == ord(" "):
            break

        # Ukur waktu pemrosesan loop
        loop_end_time = time.time()
        print(f"Loop time: {loop_end_time - loop_start_time:.2f} seconds")

except KeyboardInterrupt:
    print('Stopped by KeyboardInterrupt')

finally:
    # Hentikan pengumpulan data otomatis
    ser.write(serial.to_bytes([0xA5, 0x25, 0x01, 0xCB]))
    ser.close()
    cv2.destroyAllWindows()
    # Stop loop MQTT
    client.loop_stop()
    # Putuskan sambungan dari broker MQTT
    client.disconnect()
    print('Resources cleaned up')

# Just in case 
ser.close()
cv2.destroyAllWindows()
