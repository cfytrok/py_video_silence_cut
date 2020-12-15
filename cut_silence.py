import os
import re
import shutil
import argparse
import subprocess
import datetime


def runcmd(cmd):
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    return (out.stdout or out.stderr).decode('cp866')


def get_silence_level(file_path):
    """Определяет уровень тишины, как уровень максимальной громкости - 25дБ"""
    stdout = runcmd(['ffmpeg', '-i', file_path, '-af', 'volumedetect', '-vn', '-sn', '-dn', '-f', 'null', 'null'])
    max_volume = re.search(r'max_volume: ([-\d.]+)', stdout).group(1)
    mean_volume = re.search(r'mean_volume: ([-\d.]+)', stdout).group(1)
    return float(max_volume) - 25


def get_video_files(path):
    for file in os.listdir(path):
        if os.path.isfile(os.path.join(path, file)) and re.match(r'(.*\.(mp4|avi)$)', file.lower()):
            yield file


class VideoCutter:

    def __init__(self, tmp_folder, silence_level=None, silence_duration=0.5, sound_duration=0.2, before_sound=0.1,
                 after_sound=0.2):
        self.silence_level = silence_level
        self.silence_duration = silence_duration
        self.sound_duration = sound_duration
        self.before_sound = before_sound
        self.after_sound = after_sound
        self.tmp_folder = tmp_folder

    def get_sound_timestamps(self, in_file_path, silence_level, silence_duration):
        if not silence_level:
            silence_level = get_silence_level(in_file_path)
        timestamps_path = os.path.join(self.tmp_folder, 'timestamps.txt')
        # command = 'ffmpeg -i "%s" -af silencedetect=noise=%s:d=%s -f null - 2> %s' % (
        # in_file_path, silence_level, silence_duration,timestamps_path)
        command = ['ffmpeg', '-i', in_file_path, '-af',
                   'silencedetect=noise=%sdB:d=%s' % (silence_level, silence_duration), '-f', 'null', 'null']

        ffout = runcmd(command)
        # os.system(command)
        # with open(timestamps_path, 'r', encoding='utf8') as f:
        #     filetext = f.read()
        starts = re.findall(r'silence_start: (.+)', ffout)
        starts = list(map(lambda x: round(float(x), 2), starts))
        ends = re.findall(r'silence_end: ([^ ]+)', ffout)
        ends = list(map(lambda x: round(float(x), 2), ends))
        intervals_with_sound = list(zip(*(ends, starts[1:])))
        duration = re.search(r'Duration: ([^ ,]+)', ffout).group(1)
        duration = datetime.datetime.strptime(duration, '%H:%M:%S.%f')
        duration = (duration - datetime.datetime(1900, 1, 1)).total_seconds()
        if starts and starts[0] >= self.sound_duration:
            intervals_with_sound.insert(0, (0, starts[0]))
        if ends and len(starts) == len(ends):
            intervals_with_sound.append((ends[-1], duration))
        return intervals_with_sound

    def process_ffmpeg_partly(self, intervals_with_sound, in_filename, out_filename):
        """В выходный файл попадают только интервалы, в которых есть звук"""
        parts = []
        parts.append(
            "[0:v]trim=start=%(start).2f:end=%(end).2f,setpts=PTS-STARTPTS[%(sec_i)sv];[0:a]atrim=start=%(start).2f:end=%(end).2f,asetpts=PTS-STARTPTS[%(sec_i)sa]" % {
                'start': max(0, intervals_with_sound[0][0] - self.before_sound),
                'end': intervals_with_sound[0][1] + self.after_sound, 'sec_i': 0})
        last_i_count = 0
        for i, (start, end) in enumerate(intervals_with_sound[1:]):
            if float(end) - float(start) >= self.sound_duration:
                parts.append(
                    "[0:v]trim=start=%(start).2f:end=%(end).2f,setpts=PTS-STARTPTS[%(sec_i)sv];[0:a]atrim=start=%(start).2f:end=%(end).2f,asetpts=PTS-STARTPTS[%(sec_i)sa];[%(first_i)sv][%(sec_i)sv]concat[%(third_i)sv];[%(first_i)sa][%(sec_i)sa]concat=v=0:a=1[%(third_i)sa]" % {
                        'start': start - self.before_sound, 'end': end + self.after_sound, 'first_i': last_i_count * 2,
                        'sec_i': i * 2 + 1,
                        'third_i': i * 2 + 2})
                last_i_count = i + 1
        command = 'ffmpeg -i "%s" -filter_complex "%s" -map [%s] -map [%s] "%s"' % (
            in_filename, '; '.join(parts), '%sv' % (last_i_count * 2), '%sa' % (last_i_count * 2), out_filename)
        subprocess.run(command)

    def process_video(self, in_folder, in_filename, out_folder):
        # очищаем папку temp или создаем ее
        if os.path.exists(self.tmp_folder):
            shutil.rmtree(self.tmp_folder)
        os.makedirs(self.tmp_folder)

        name, extention = os.path.splitext(in_filename)
        in_file_path = os.path.join(in_folder, in_filename)
        out_file_path = os.path.join(out_folder, in_filename)
        intervals_with_sound = self.get_sound_timestamps(in_file_path, self.silence_level, self.silence_duration)
        if not intervals_with_sound:
            # тишина не найдена, просто копируем файл
            shutil.copyfile(in_file_path, out_file_path)
        else:
            # нарезаем видео на отрезки со звуком
            step = 150
            files = []
            file_names_file = 'concat_files.txt'
            file_names_path = os.path.join(self.tmp_folder, file_names_file)
            with open(file_names_path, 'w') as f:
                for i in range(0, len(intervals_with_sound), step):
                    filename = '__%s_%s.mp4' % (i, name)
                    file_path = os.path.join(tmp_folder, filename)
                    self.process_ffmpeg_partly(intervals_with_sound[i:i + step], in_file_path, file_path)
                    f.write("file '%s'\n" % file_path)
                    files.append(file_path)
            # склеиваем отрезки в один файл
            command = 'ffmpeg -f concat -safe 0 -i %s -c copy "%s"' % (file_names_path, out_file_path)
            subprocess.run(command)

        # удаляем папку с временными файлами
        shutil.rmtree(self.tmp_folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Убирает тишину из видео')
    parser.add_argument('-i', "--in_path", help="Путь к папке с исходными видео (default: video в workdir)")
    parser.add_argument('-o', "--out_path", help="Путь к папке с обрезанными видео (default: video_short в workdir)")
    parser.add_argument('-sl', "--silence_level",
                        help="Уровень в дБ ниже которго считаем, что на видео тишина (default: max_level-25dB)")
    parser.add_argument('-sd', "--silence_duration",
                        help="Минимальная длительность интервала c тишиной в секундах, что бы он был вырезан (default: 0.5)",
                        type=float, default=0.5)
    parser.add_argument('-sndd', "--sound_duration",
                        help="Минимальная длительность интервала со звуком в секундах, что бы он прошел на выход (default: 0.1)",
                        type=float, default=0.1)
    parser.add_argument('-bs', "--before_sound_interval",
                        help="Сколько времени в секундах надо добавить до начала звука (default: 0.1)", type=float,
                        default=0.1)
    parser.add_argument('-as', "--after_sound_interval",
                        help="Сколько времени в секундах надо добавить после окончания звука (default: 0.2)",
                        type=float, default=0.2)
    args = parser.parse_args()
    work_dir = os.getcwd()

    if args.before_sound_interval + args.after_sound_interval >= args.silence_duration:
        raise Exception("Суммарная длительность интервалов до и после звука не может быть больше тишины")

    if args.in_path:
        in_folder = args.in_path
    else:
        in_folder = os.path.join(work_dir, 'video')

    if args.out_path:
        out_folder = args.out_path
    else:
        out_folder = in_folder + '_short'

    tmp_folder = os.path.join(work_dir, 'tmp')

    if not os.path.exists(out_folder):
        os.makedirs(out_folder)
    in_files = list(get_video_files(in_folder))

    vc = VideoCutter(tmp_folder, args.silence_level, args.silence_duration, args.sound_duration,
                     args.before_sound_interval, args.after_sound_interval)

    for in_filename in in_files:
        vc.process_video(in_folder, in_filename, out_folder)
