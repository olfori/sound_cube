'''
Распознаю одно слово, принятое микрофоном
АЛГОРИТМ
Всегда работают 2 процесса:

'''
import wave
import time
import math
import struct
import threading
import os
from os import path
import numpy as np
import pyaudio
from pocketsphinx import get_model_path
from pocketsphinx.pocketsphinx import *

modeldir = get_model_path() #директория, где лежат файлы словаря PocketSphinx
md = path.dirname(__file__)

# Create a decoder with certain model
config = Decoder.default_config()
config.set_string('-logfn', '/dev/null')
config.set_string('-hmm', os.path.join(modeldir, 'en-us'))
config.set_string('-dict', os.path.join(md, '8070.dic'))
config.set_string('-lm', os.path.join(md, '8070.lm'))

THRESHOLD = 15  # Порог громкости, если звук выше - сработает распознавание
PRE_REC_LEN = 3 # длина предзаписи(чтоб ловить начало слова)
REC_LEN = 8    # длина записи самого слова

SHORT_NORMALIZE = (1.0/32768.0)
CHUNK = 6144    # длина массива для записи 1 кванта звука для 48КГц
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000

# Здесь лежат нужные слова, если одно из этих слов распознано - Загадка решена!
FNAME = path.join(path.dirname(__file__), 'wrds.txt')

def test():
    '''Test for pyaudio - print devices and characteristic'''
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        print((i,dev['name'], dev['maxInputChannels']))
    print("-"*34)
    for x in range(p.get_device_count()):
        print(p.get_device_info_by_index(x))
    print("-"*34)

class Recognizer:
    '''Класс для записи и распознавания речи'''

    def __init__(self):
        # Список слов, с которыми сравниваются распознаваемые слова
        self.li_correct_words = []
        self.read_correct_words_from_file(12) #  Читаю .. правильных слов из ф-ла

        self.st = (b'\x00\x00' * CHUNK) # текущий кусок звука
        self.recognize = True       # Флаг, разрешающий распознавание
        self.buf = []   # список сохраненных кусков звука
        self.cc = 0     # главный счетчик - управляет всеми процессами
        self.c = 0      # тестовый счетчик, для проверки записи в файл

        self.correct_wrd = 0
        self.was_recognition = 0
        self.start_recognition = 0

        self.threshold = THRESHOLD
        self.rec_len = REC_LEN

        # инициализация pyaudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  input=True,
                                  output=False,
                                  input_device_index = 1, # для распберри
                                  frames_per_buffer=CHUNK)

        # Запускаю процесс слушания микрофона
        self.thread = threading.Thread(target=self.stream_listen)
        self.thread.start()         

        # Запускаю декодер Pocketsphinx для распознавания слов
        self.decoder = Decoder(config)
        self.decoder.start_utt()

        #thread = threading.Thread(target=self.listen)
        #thread.start()

    def rms(self):
        '''Вычисляю RMS входного сигнала, типа амплитуда'''
        li_ = struct.unpack("h"*512, self.st[:1024])
        arr = np.array(li_, np.int) / 32768
        sum_sq = np.sum(arr*arr)
        rms_ = math.pow(sum_sq / 512, 0.5)
        return int(rms_ * 1000)

    def read_correct_words_from_file(self, how_many_wrds):
        '''читаю слова из тхт файла в список'''
        with open(FNAME, 'r') as f:
            for i, wrd in enumerate(f):
                if i < how_many_wrds:
                    wrd = ''.join(e for e in wrd if e.isalnum())
                    #print(wrd)
                    self.li_correct_words.append(wrd)
            f.close()

    def stream_listen(self):
        '''поток управляет предзаписью, записью, распознаванием звука'''
        while self.recognize:
            # если счетчик != 1, читаю в self.st глыбу звука
            if self.cc != 1:
                try:    # попытка достать глыбу байтов с микрофона
                    self.st = self.stream.read(CHUNK)
                except IOError as ex:
                    #print(ex)
                    self.st = (b'\x00\x00' * CHUNK * CHANNELS)

            if not self.cc:         # если счетчик = 0, делаю предзапись
                self.pre_rec()

            if self.cc > 1:         # если счетчик больше 1
                self.buf.append(self.st)    # добавляю глыбы(кванты) звука в общ запись

            if self.cc == 1:        # когда счетчик записи == 1
                try:
                    self.stream.stop_stream()   # остановить запись
                except IOError as ex:
                    print('problem 1')
                    print(ex)
                self.recognize_word()    # распознаю слово в записи
                print('self.correct_wrd in recognizer', self.correct_wrd)
                #self.write()
                self.buf = []       # обнулить буфер
                self.was_recognition = 1
                if self.recognize:  # если разрешен поток прослушивания
                    self.stream.start_stream()  # запустить прослушивание

            if self.cc:             # если счетчик больше нуля
                self.cc -= 1        # уменьшить счетчик на 1
                print(self.cc)

    def pre_rec(self):
        ''' пред запись - сохраняю в массив куски звука и сдвигаю на 1 влево'''
        l_ = len(self.buf)
        if l_ < PRE_REC_LEN:
            self.buf.append(self.st)
        else:
            for i in range(l_-1):
                if i < l_-1:
                    self.buf[i] = self.buf[i+1] # сдвиг списка на 1 влево
                else:
                    self.buf[i] = self.st       # обновляю последний элемент

    def convert_48k_to16k(self, li_chunk):
        '''Программный конвертер 48 КГц в 16 КГц, тк 16 КГц нет в микрофоне'''
        res_li_chunk = []
        for chunk in li_chunk:
            chunk = struct.unpack('h'*CHUNK, chunk)
            chunk = list(chunk[::3])
            res_li_chunk.append(struct.pack('h'*len(chunk), *chunk))
        return res_li_chunk

    def recognize_word(self):
        '''Метод, распознающий введенное слово'''
        recording = self.convert_48k_to16k(self.buf) # Сконвертировал в 16 КГц
        for ch in recording:        # Декодирую звук в текст с пом. Pocket Sphinx
            self.decoder.process_raw(ch, False, False)
        if self.decoder.hyp() != None:  # Если есть варианты (текст с вых Sphinx)
            self.correct_wrd = -1
            for seg in self.decoder.seg():  # Перебираю полученные слова
                print(seg.word)
                if self.check_word(seg.word):# Если "Protego" есть в выдаче
                    self.correct_wrd = 1
                    print('Bellissimo! Protego!')
            self.decoder.end_utt()      # обнуляю декодер
            if self.correct_wrd == 1:
                self.stop_all()
                print('listening stoped')
            else:
                self.decoder.start_utt()
                print('Returning to listening')

    def stop_all(self):
        '''останавливаю все потоки, запрещаю циклы - полный стоп'''
        self.recognize = False
        try:
            self.stream.close()
        except IOError as ex:
            print('problem 3')
            print(ex)
        self.p.terminate()

    def check_word(self, word):
        '''сравниваю каждое слово со словами из тхт файла правильных слов'''
        if word.lower() in self.li_correct_words:
            return True
        return False

    def write(self):
        '''Метод для записи звука с микрофона в файл(исп только для проверки)'''
        recording = self.convert_48k_to16k(self.buf)
        recording = b''.join(recording)
        filename = os.path.join(md, str(self.c)+'ss.wav')
        self.c += 1
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.p.get_sample_size(FORMAT))
        wf.setframerate(16000)
        wf.writeframes(recording)
        wf.close()
        print('Written to file: {}'.format(filename))
        print('Returning to listening')
        time.sleep(1)

    def check_allow_recognition(self):
        '''разрешить распознавание'''
        if self.rms() > THRESHOLD: # Если RMS больше порогового значения
            if self.start_recognition:
                self.start_recognition = 0
                self.cc = REC_LEN   # разрешаю распознанвание

    def listen(self):
        '''Процесс прослушивания микрофона и старта записи, если RMS > порога'''
        print('Listening beginning')
        while self.recognize:   # Пока разрешено распознавание
            if not self.cc:     # Если счетчик циклов записи = 0
                self.check_allow_recognition()


if __name__ == '__main__':
    #test()
    A = Recognizer()
    #A.listen()
