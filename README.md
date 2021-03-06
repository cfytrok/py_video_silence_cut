Скрипт для командной строки. Автоматически вырезает тишину из видео, используя ffmpeg.
# Установка
Перед запуском нужно установить [ffmpeg](https://ffmpeg.org/).

# Пример использования

Положите видео, которые нужно обрезать в папку video и выполните код в командной строке. В video_short появятся видео с вырезанной тишиной.

```
python cut_silence.py
```

Вызов справки по параметрам.
```
python cut_silence.py -h
```

# Как это работает
1. Использует ffmpeg silencedetect для определения отрезков тишины на видео.
2. Отрезки видео со звуком группируются (для увеличения скорости работы). И для каждой группы формируется видео, которое состоит только из отрезков со звуком.
3. Полученные на предыдущем этапе файлы объединяются в один файл.

Операция повторяется для каждого видео в исходной папке.

# Как определяется тишина
По умолчанияю тишина - это звук с громкостью на 25dB ниже максимальной громкости в видео.
Можно задать свой уровень тишины в дБ в параметре --silence_level
Так же можно задать минимальную длительность тишины, звука, а так же время которое нужно сохранить перед и после интервала со звуком.