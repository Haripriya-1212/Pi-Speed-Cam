import pika, sys, os, serial
from queueing import Queue
from threading import Thread
from time import sleep
from io import BytesIO

from dotenv import load_dotenv

from picamera import PiCamera
from gpiozero import Buzzer

load_dotenv()

def main():
    speed_limit = Queue()
    speed_limit.put(40)
    
    buzzer = Buzzer(17)
    
    url = os.getenv("CLOUDAMQP_URL")
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(queue='video')
    channel.queue_declare(queue='speed')
    channel.queue_declare(queue='report')

    i = 1
    def poll_camera_capture():
        nonlocal i, channel

        capture_stream = BytesIO()
        camera = PiCamera()
        camera.start_preview()

        sleep(2)
        print("Stared polling Camera Capture")

        while(True):
            camera.capture(capture_stream, 'jpeg')
            capture_stream.seek(0)
            channel.basic_publish(exchange='', routing_key='video', body=capture_stream.read())
            print(f"Published Frame: {i}")
            i = i + 1
            sleep(1)


    def ring_buzzer():
        nonlocal buzzer
        buzzer_time = 4
        
        buzzer.on()
        sleep(buzzer_time)
        buzzer.off()
        

    def speed_callback(ch, method, properties, body):
        nonlocal channel, speed_limit
        
        speed_lim_val = int(body)
        print(f"Received Speed Limit: {speed_lim_val}")

        speed_limit.get()
        speed_limit.put(speed_lim_val)
       
       
    def check_speed():
        nonlocal speed_limit
        
        gprmc_info = "$GPRMC,"
        ser = serial.Serial("/dev/serial0")
        
        while True:
            data = (str)(ser.readline())
            GPRMC_data = data.find(gprmc_info)
            if(GPRMC_data>0):
                knots = data.split(',')[7]
                current_speed = float(knots) * 1.852
                # speed_lim_val = Get speed limit from queue or some other method here
                if current_speed > speed_lim_val:
                    ring_buzzer()
                    channel.basic_publish(exchange='', routing_key='report', body='Speeding Found!')


    channel.basic_consume(queue='speed', on_message_callback=speed_callback, auto_ack=True)

    thread = Thread(target=poll_camera_capture)
    cs_thread = Thread(target=check_speed)
    
    thread.start()
    cs_thread.start()

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)