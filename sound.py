'''
Реализую воспроизведение звуков для "Куб"
АЛГОРИТМ: - один поток - Главный цикл

Главный цикл = main_cycle()
- Жду активации = wait_for_activation()
- Пауза с выводом обратного отсчета, можно выбрать язык, пока пауза
- Объявляю, выбранный язык
- Проверил, включен-ли Демо-режим
- если выбран обычный режим
  - запускаю ЦИКЛ СЧИТЫВАНИЯ СИГНАЛОВ
- если выбран демо режим
  - в цикле проигрываю демо мелодию
  - жду нажатия сброса

Цикл считывания сигналов = read_signals()
- играет вступительная речь
 Цикл:
 - проверяю приход нового сигнала = check_new_sig() (запомнил номер сигнала в sig)
 - действия для сиг1
 ...
 - действия для сиг10

Проверка прихода нового сигнала = check_new_sig()
- если не Демо режим
  - если новый сигнал: стоп звуки, запомнил номер сигнала
  - если нажата подсказка: запускаю подсказку
- если Демо режим
  - жду нажатия кнопки сброс

'''
import time
import pygame
#import RPi.GPIO as GPIO # для Raspberry(без эмулятора)
import GPIOEmu as GPIO   # для проверки в Убунту
import threading
from oneWordRecognizer import *

FIRST_DELAY = 5  # 15 пауза после того, как убрали sig1 (перед голос_1)
# Если REPLAY_TIME = 0 - повтор отключен
REPLAY_TIME = 0  # 5 через ск МИНУТ однократно повторить голос 2..6

SIG_1_IN = 14
SIG_2_IN = 15
SIG_3_IN = 18
SIG_4_IN = 23
SIG_5_IN = 1
SIG_6_IN = 12
SIG_7_IN = 16
SIG_8_IN = 20
SIG_9_IN = 21
SIG_10_IN = 26

LANG_BTN_EN = 4
LANG_BTN_RU = 27

HELP_BTN = 10
GERK = 22

SIG_OUT_1 = 19
# r, g, b pins raspberry
RGB = [ 6, 5, 13] 
# Raspberry sig in pins
SIG_IN = [0, SIG_1_IN, SIG_2_IN, SIG_3_IN, SIG_4_IN, SIG_5_IN,
          SIG_6_IN, SIG_7_IN, SIG_8_IN, SIG_9_IN, SIG_10_IN]
# Raspberry out pins
SIG_OUT = [0, SIG_OUT_1]
# main sound directory
DIR_MP3 = path.join(path.dirname(__file__), 'mp3')
# Фоновые звуки. Они лежат только в папке mp3
BG_SND = {1:'b1.mp3', 2:'b2.mp3', 3:'b3.mp3', 4:'b4.mp3', 5:'b5.mp3',
            6:'solved_riddle.mp3', 7:'demo.mp3'}
# Озвучка голосов (лежит в 3 папках en, ru, ua)
VOICE_SND = {1:'v1.mp3', 2:'v2.mp3', 3:'v3.mp3', 4:'v4.mp3', 5:'v5.mp3',
            6:'v6.mp3', 7:'v7.mp3', 8:'lang.mp3', 9:'recogn.mp3'}
# Озвучка подсказок (лежит в 3 папках en, ru, ua !!!wav файлы обязательно!!!)
HELP_SND = {2:'h2.wav', 3:'h3.wav', 4:'h4.wav', 5:'h5.wav', 6:'h6.wav', 
            7:'h7.wav', 8:'h8.wav', 9:'h9.wav', 10:'h1.wav'}
# Алгоритм считывания сигналов           
# Sig num : [need a replay?, need a Solved riddle sound?, voice snd, bg sound]
READ_ALG = {2:[1, 1, 2, 1], 3:[1, 1, 3, 5], 4:[0, 1, 0, 2], 5:[1, 1, 4, 5],
            6:[0, 1, 0, 3], 7:[1, 1, 5, 5], 9:[0, 1, 0, 4], 10:[0, 0, 7, 0]}

def led(color_num):
    '''включаю подсветку нужного цвета. 0-красн. 1-зел. 2-синий'''
    for i, pin_color in enumerate(RGB):
        GPIO.output(pin_color, GPIO.LOW)
        if i == color_num:
            GPIO.output(pin_color, GPIO.HIGH)

class Sound:
    '''Класс, реализующий воспроизведение звуков по заданному алгоритму'''

    def __init__(self):
        self.flag = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        self.sig = 0
        self.demo = 0
        self.replay_tm = 0

        self.rec = 0  # флаг, что распознавание слова прошло успешно
        self.vr = {'started':0, 'correct':0, 'bps':0} # флаги расп голоса

        self.lang = ['ua', '']  # 0 - lang,  1 - last_lang

        self.GPIOsetup()    # инициализировал пины распберри

        self.check_lang()  # Проверил, нажата-ли кнопка выбора яз. и выставил язык

        print(self.lang[0])  # показал текущ язык

        pygame.mixer.init()
        self.mus = pygame.mixer.music
        self.mus.set_volume(1.0)

        self.mus1 = pygame.mixer.music
        self.mus1.set_volume(1.0)

    def check_lang(self):
        '''Установка выбранного языка, в соответствии с нажатыми кнопками выбора языка'''
        if GPIO.input(LANG_BTN_EN):
            self.lang[0] = 'en'
        elif GPIO.input(LANG_BTN_RU):
            self.lang[0] = 'ru'
        else:
            self.lang[0] = 'ua'

        if self.lang[0] != self.lang[1]:
            self.lang[1] = self.lang[0]
            print('Lang was changed, now it\'s', self.lang[0])

    def pass_recognition(self):
        bps8 = self.sig == 8 and GPIO.input(SIG_8_IN)
        if bps8:
            return 1

    def before_recognize(self):
        '''вкл подсветку, жду сработку геркона, вкл звук "произнесите заклинание"'''
        led(2) # вкл синюю подсветку
        print('Gerk wait for magic stick, only reset_btn can help you out of here')
        # Если еще не распознан голос
        if not self.rec:
            while GPIO.input(GERK) and not self.rec: # жду сработку геркона
                if not GPIO.input(SIG_IN[1]):    # если пришел сигнал 1 (reset)
                    self.reset()
                if self.pass_recognition():
                    return

            self.play_sound(self.voice_path(9), no_sig=1)
            print('Listening begin')

    def correct_vr(self):
        led(1) # вкл зеленую подсветку
        GPIO.output(SIG_OUT_1, GPIO.HIGH)   # отправил сигнал

    def voice_recognition(self):
        '''Распознавание произнесенного слова'''
        r = Recognizer()
        self.before_recognize()
        print('this cod be only one time')

        while r.recognize:
            if self.pass_recognition():
                r.stop_all()        # закончить распознавание, загадка решена
                self.correct_vr()

            if r.was_recognition:
                r.was_recognition = 0
                # Если произнесено правильное заклинание
                if r.correct_wrd == 1:
                    print('r.correct_wrd', r.correct_wrd)
                    r.stop_all()        # закончить распознавание, загадка решена
                    self.correct_vr()
                    break

                # Если произнесено неверное заклинание
                if r.correct_wrd == -1:
                    r.correct_wrd = 0
                    print('r.correct_wrd', r.correct_wrd)
                    led(0) # вкл красную подсветку
                    self.before_recognize()

            '''
            # Здесь разрешаю распознавание
            if not r.cc:
                if r.rms() > THRESHOLD: # если громк звука больше порог знач
                        r.allow_r()

            # if r.try_counter == 6: # Если было ... неправильн попытки
            #   r.stopAll()        # закончить распознавание - решить загадку
            #if time.time() - r.start_time > 60:  # Если загадка не решается > ... сек
            #    r.stopAll()        # закончить распознавание - решить загадку
            '''

    def GPIOsetup(self):
        '''Настраиваю GPIO'''
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        li_all_out = SIG_OUT + RGB
        for pin in li_all_out:
            if pin:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)

        li_all_inp = SIG_IN + [LANG_BTN_EN, LANG_BTN_RU, HELP_BTN, GERK]
        for pin in li_all_inp:
            if pin:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def check_new_sig(self):
        '''Проверяю, пришел-ли новый сигнал'''

        # Проверяю переключение языка во время игры
        #self.check_lang()

        self.replay()

        # если не демо режим
        if not self.demo:
            for num, pin in enumerate(SIG_IN):
                # Если не нулевой пин
                # и если есть сигнал на пине
                # и если этот сигнал еще не приходил
                if pin and not GPIO.input(pin) and self.flag[num]:
                    self.mus.stop()   # останов муз
                    self.sig = num              # запомнил номер сигн

            # реакция на кн. help
            if not GPIO.input(HELP_BTN):
                while not GPIO.input(HELP_BTN):
                    time.sleep(0.05)
                self.help()     # сработает, когда отжата кнопка
            
            return True

        # если демо режим
        else:
            if not GPIO.input(SIG_IN[1]):    # если пришел сигнал 1 (reset)
                self.mus.stop()

    def play_wav_on_top(self, f_name):
        '''Играть файл поверх текущего(только wav), текущий ставится на паузу'''
        f_name = path.join(DIR_MP3, f_name)
        print(f_name)
        self.mus.pause()
        snd = pygame.mixer.Sound(f_name)
        snd_len = snd.get_length()
        snd.play()
        time.sleep(snd_len)
        self.mus.unpause()

    def play_sound(self, f_name, loop=0, no_sig=0):
        '''Проигрываю звуковой файл (имя, зацикливание = -1, без проверки сиг)'''
        print("SIG_IN", self.sig)

        f_name = path.join(DIR_MP3, f_name)

        self.mus.stop()
        self.mus.load(f_name)
        self.mus.play(loop)
        while self.mus.get_busy():
            if no_sig:
                continue
            else:
                self.check_new_sig()

        time.sleep(0.2)

    def reset(self):
        '''Сброс параметров - эмуляция перезагрузки'''
        self.flag = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        GPIO.output(SIG_OUT[1], GPIO.LOW)
        self.sig = 0
        self.demo = 0
        self.main_cycle()

    def help_path(self, h_num):
        '''sets the help voices directory, considering the selected language'''
        return path.join(self.lang[0], HELP_SND[h_num])

    def help(self):
        print('this must be helpfull: sig_', self.sig)
        for sig in HELP_SND:
            if sig == self.sig:
                self.play_wav_on_top(self.help_path(sig))
                
    def voice_path(self, v_num):
        '''sets the voice directory, considering the selected language'''
        return path.join(self.lang[0], VOICE_SND[v_num])

    def replay(self):
        '''метод для повтора подсказки через заданный промежуток времени'''

        # если replay_tm != 0 и REPLAY_TIME != 0, вкл повтора голоса
        if self.replay_tm and REPLAY_TIME:
            # через REPLAY_TIME минут
            if time.time() - self.replay_tm > REPLAY_TIME*60:
                # Прохожу по списку сигналов с повторами
                for sig in READ_ALG:
                    voice_num = READ_ALG[sig][2]
                    if sig == self.sig and voice_num:
                        self.replay_tm = 0
                        print("replaying voice_snd", voice_num)
                        f_name = path.join(DIR_MP3, self.voice_path(voice_num))
                        self.mus.pause()
                        self.mus1.load(f_name)
                        self.mus1.play()
                        while self.mus1.get_busy():
                            continue
                        self.mus.unpause()

    def read_signals(self):
        '''цикл обработки сигналов во время игры'''

        while 1:
            time.sleep(0.1)  # Пауза процесса

            self.check_new_sig()

            if self.sig == 1:
                print("SIG_IN 1 reset all, restart")
                self.replay_tm = 0
                self.reset()
                break

            for sig in READ_ALG:
                if sig == self.sig and self.flag[sig]:
                    self.flag[self.sig] = 0

                    need_replay = READ_ALG[sig][0]
                    if need_replay:
                        self.replay_tm = time.time()
                    
                    need_solved_riddle_snd = READ_ALG[sig][1]
                    if need_solved_riddle_snd:
                        self.play_sound(BG_SND[6])
                    
                    voice_num = READ_ALG[sig][2]
                    if voice_num:
                        self.play_sound(self.voice_path(voice_num))

                    bg_num = READ_ALG[sig][3]
                    if bg_num:
                        self.play_sound(BG_SND[bg_num], -1)

            if self.sig == 8 and self.flag[8]:
                self.flag[8] = 0
                self.play_sound(BG_SND[6])
                self.voice_recognition()
                self.replay_tm = time.time()
                self.play_sound(BG_SND[6])
                self.play_sound(self.voice_path(6))
                self.play_sound(BG_SND[5], -1)
                    
    def wait_for_activation(self):
        '''жду прихода сиг1'''
        while 1:
            time.sleep(0.1)
            self.check_lang()
            # Пока есть sig_1, квест не активен
            if GPIO.input(SIG_IN[1]):
                print("!SIG_IN[1] => sig1 left us")
                break   # выхожу из первого while

    def main_cycle(self):
        '''Главный цикл здесь'''
        self.wait_for_activation()

        # Произношу, выбранный язык
        self.play_sound(self.voice_path(8), no_sig=1)

        # пауза с выводом обратного отсчета + выбор языка
        for i in range(FIRST_DELAY):
            t_left = FIRST_DELAY-i
            led(t_left-2)
            print('Wait {} sec'.format(t_left))
            time.sleep(1)

        # Проверил, включен-ли Демо-режим? сиг2 и сиг10 = Демо режим
        if not GPIO.input(SIG_IN[2]) and not GPIO.input(SIG_10_IN):
            self.demo = 1

        # если выбран обычный режим (не демо)
        if not self.demo:
            self.play_sound(self.voice_path(1))
            self.sig = 0
            print('Start reading signals')
            self.read_signals()

        # если выбран демо режим
        else:
            self.sig = 0
            self.play_sound(BG_SND[7], -1) # зациклено здесь
            print("Demo stop, SIG_IN[1] reset all, restart")
            self.reset()

        self.main_cycle()  # по выходу из второго while, ф-ция запустится заново


if __name__ == '__main__':
    # для воспроизв Pyaudio на аудио вых
    os.system('amixer -c 0 cset numid=3 1')
    S = Sound()
    S.main_cycle()
