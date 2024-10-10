#!/usr/bin/env python3

import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.options
from tornado.options import define, options

import time, math, struct, threading
from collections import deque
from math import pi
from yarc import Roomba

define("port", type=int, default=8888, help="port to listen on")
define("debug", type=bool, default=False, help="debug mode")
define("usb_port", type=str, default='/dev/ttyUSB0', help='the USB port to use for the serial connection')

bot = None

class Robot(threading.Thread):
    max_speed = 500 # mm/s
    max_accel = 375 # mm/s^2
    max_decel = 1500 # mm/s^2

    __cur_mode, __target_mode = 0, 1
    __target_l, __target_r = 0, 0
    __last_event = None

    def __init__(self):
        super().__init__()
        self.__listeners = []
        self.__queue = deque()
        self.bot = Roomba(options.usb_port)
        self.bot.start()
        self.event = threading.Event()
        self.start()

    def stop(self):
        self.event.set()
        self.join()

    def run(self):
        try:
            #last_change_time =
            last_time = time.perf_counter()
            #set_mode_attempts = 0
            l,r = 0,0

            time.sleep(0.015)
            self.__cur_mode = self.__get_mode()
            self.__fire_status_listeners()

            while not self.event.wait(0.015):
                self.__cur_mode = self.__get_mode()
                if self.__target_mode is not None and self.__cur_mode != self.__target_mode:
                    #set_mode_attempts += 1
                    #if set_mode_attempts >= 6:
                    #    print("reseting")
                    #    self.bot.reset()
                    #    set_mode_attempts = 0
                    if   self.__target_mode == 1: self.bot.start()
                    elif self.__target_mode == 2: self.bot.safe()
                    elif self.__target_mode == 3: self.bot.full()
                    time.sleep(0.015)
                    self.__cur_mode = self.__get_mode()
                else: self.__target_mode = None
                #else: set_mode_attempts = 0

                cur_time = time.perf_counter()
                if self.__target_l != l or self.__target_r != r:
                    l, r = self.__update_velocity(l, r, cur_time - last_time)
                #    last_change_time = cur_time
                #elif self.__cur_mode >= 2 and cur_time - last_change_time >= 10*60:
                #    self.bot.power() # after 10 minutes go to sleep
                #    self.__target_mode = 0
                last_time = cur_time
                self.__fire_status_listeners()

                # Run a single operation from the queue
                if self.__queue:
                    retval = self.__queue.popleft()()
                    if retval is not None: l,r = retval
        except Exception as ex:
            print(ex)
            for listener in self.__listeners: listener('error', None, None)
        finally:
            self.__queue.clear()
            self.bot.close()

    def add_listener(self, callback):
        self.__listeners.append(callback)
        return len(self.__listeners)
    def remove_listener(self, callback):
        self.__listeners.remove(callback)
        return len(self.__listeners)
    def __fire_status_listeners(self):
        if len(self.__listeners) == 0: return # don't bother if no one is listening

        # Get the battery information
        # (un-)plugging from the base can cause the robot to sleep, wake it up!
        cs,bp = -1,-1
        for _ in range(2):
            try:
                cs = self.bot.charging_state.value
                bp = round(self.bot.battery_charge / self.bot.battery_capacity, 2)
                break
            except (ValueError, struct.error): pass
            self.bot.wake()

        # Make the event
        event = (self.__cur_mode, cs, bp)
        if event == self.__last_event: return # don't announce it if nothing has changed
        self.__last_event = event

        # Broadcast the event
        for listener in self.__listeners: listener(*event)

    def add_op(self, op):
        if not callable(op): raise TypeError()
        self.__queue.append(op)
    
    def reset(self):
        if threading.current_thread() != self:
            self.__queue.append(self.reset)
            return
        self.bot.reset()
        self.bot.start()
        self.__cur_mode, self.__target_mode = 0, 1
        self.__target_l, self.__target_r = 0, 0
        self.__last_event = None
        return 0, 0

    def play_song(self):
        if threading.current_thread() != self:
            self.__queue.append(self.play_song)
            return

        # Part 1 - 7.5
        notes = ['A4','D5','F5','E5','F5','E5','D5','F5','E5','F5','D5','E5','F5','E5','F5','D5']
        durations = [ 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 100]
        self.bot.create_song(0, notes, durations)

        # Part 2 - 7.5
        notes = ['C5','F5','A5','G5','A5','G5','F5','A5','G5','A5','F5','G5','A5','G5','A5','F5']
        durations = [ 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 100]
        self.bot.create_song(1, notes, durations)

        # Part 3 - 5.9375
        notes = ['C6','D6','C6','D6','C6','G5','A5','C6','A5','G5','G5','F5','G5','F5']
        durations = [ 20 , 40 , 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 40 , 20 , 40 , 20]
        self.bot.create_song(2, notes, durations)

        # Part 4 - 8.125
        notes = ['C5','D5','F5','D5','C5','D5','F5','C5','F5','D5','E5','F5','C5','A5','G5','F5']
        durations = [ 20 , 20, 20 , 40 , 20 , 40 , 20 , 40 , 20 , 20 , 20 , 20 , 40 , 20 , 120 , 40]
        self.bot.create_song(3, notes, durations)

        # Start playing the song
        self.bot.play_song(0)
        self.__queue.append(self.__play_song_1)
    def __play_song_1(self):
        if self.bot.song_playing: self.__queue.append(self.__play_song_1)
        else: self.bot.play_song(1); self.__queue.append(self.__play_song_2)
    def __play_song_2(self):
        if self.bot.song_playing: self.__queue.append(self.__play_song_2)
        else: self.bot.play_song(2); self.__queue.append(self.__play_song_3)
    def __play_song_3(self):
        if self.bot.song_playing: self.__queue.append(self.__play_song_3)
        else: self.bot.play_song(3)

    def __enforce_accel(self, target, last, dt):
        dx = target - last
        mx = self.max_decel if abs(target) < abs(last) and (target >= 0) == (last > 0) else self.max_accel
        return last + math.copysign(min(mx*dt, abs(dx)), dx)
    def __update_velocity(self, cur_l, cur_r, dt):
        # Enforce the acceleration policy on L and R motors
        l = self.__enforce_accel(self.__target_l, cur_l, dt)
        r = self.__enforce_accel(self.__target_r, cur_r, dt)

        # Make sure the motors change at the same relative rate
        dl, dr = self.__target_l - cur_l, self.__target_r - cur_r
        l_prec = 1 if dl == 0 else (l - cur_l) / dl
        r_prec = 1 if dr == 0 else (r - cur_r) / dr
        prec = min(l_prec, r_prec)
        l = int(prec*dl + cur_l)
        r = int(prec*dr + cur_r)

        # Update the speed on the bot
        self.bot.drive_direct(l, r)
        return l, r

    @staticmethod
    def __up(x): return 4/pi*x - 1 # return 2/(1+math.exp(-10*x+5*pi/2))-1
    @staticmethod
    def __down(x): return Robot.__up(pi/2-x) # 1 - 4/pi*x
    def set_motor_targets(self, x, y):
        mag = max(min(math.sqrt(x*x+y*y), 1), -1)*self.max_speed
        theta = math.atan2(y, x)
        if theta <= -pi/2:  l,r = Robot.__down(theta+pi), -1
        elif theta <= 0:    l,r = -1, Robot.__up(theta+pi/2)
        elif theta <= pi/2: l,r = Robot.__up(theta), 1
        else:               l,r = 1, Robot.__down(theta-pi/2)
        self.__target_l = l*mag
        self.__target_r = r*mag

    # Get and set the mode
    @property
    def mode(self): return self.__cur_mode
    @mode.setter
    def mode(self, mode):
        if mode <= 0 or mode > 3: raise ValueError('mode')
        self.__target_mode = mode
    def __get_mode(self):
        # (un-)plugging from the base can cause the robot to sleep, wake it up!
        # also when the bot first starts there may be an extra delay
        for _ in range(5):
            try: return self.bot.oi_mode
            except (ValueError, struct.error): pass
            self.bot.wake()
            time.sleep(0.015)
        raise ValueError()

class WebSocket(tornado.websocket.WebSocketHandler): # pylint: disable=abstract-method
    def open(self, *args, **kwargs):
        print("WebSocket opened")
        self.set_nodelay(True)

        global bot
        if bot is None: bot = Robot()
        bot.add_listener(self.listener)

    def on_close(self):
        print("WebSocket closed")

        global bot
        if bot.remove_listener(self.listener) == 0:
            bot.stop()
            bot = None

    def on_message(self, message):
        parts = message.split(' ')
        if parts[0] == 'set_motor' and len(parts) == 3:
            bot.set_motor_targets(float(parts[1]), float(parts[2]))
        elif parts[0] == 'set_mode' and len(parts) == 2:
            bot.mode = int(parts[1])
        elif parts[0] == 'reset' and len(parts) == 1:
            bot.reset()
        elif parts[0] == 'sing' and len(parts) == 1:
            bot.play_song()
        elif parts[0] != 'dummy':
            print('unknown message', parts)

    def listener(self, mode, charging_state, battery_perc):
        main_ioloop.add_callback(self.__listener, mode, charging_state, battery_perc)

    def __listener(self, mode, charging_state, battery_perc):
        try:
            if mode == 'error': self.write_message('error'); self.close()
            else: self.write_message('status %d %d %.2f'%(mode, charging_state, battery_perc))
        except tornado.websocket.WebSocketClosedError: pass

def make_app():
    return tornado.web.Application([
        (r"/websocket", WebSocket),
        (r"/(.*)", tornado.web.StaticFileHandler, {'path':'.','default_filename':'index.html'}),
    ], debug=options.debug, websocket_ping_interval=30, websocket_ping_timeout=60)

if __name__ == "__main__":
    tornado.options.parse_command_line()
    try:
        app = make_app()
        app.listen(options.port)
        main_ioloop = tornado.ioloop.IOLoop.current()
        main_ioloop.start()
    except KeyboardInterrupt: pass
    finally:
        if bot is not None:
            bot.stop()
