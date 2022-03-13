import asyncio
import hashlib
import os
import os.path
from pathlib import Path
from shutil import copyfile
from typing import Union
from multiprocessing import cpu_count

from rich import get_console
from rich.table import Column
from rich.progress import Progress, BarColumn, TextColumn
from peewee import FloatField, Model, SqliteDatabase, TextField

db = SqliteDatabase('Music.db')


class Music(Model):
    path = TextField()
    md5 = TextField(null=True)
    mtime = FloatField(null=True)

    class Meta:
        database = db


Music.create_table()


def get_md5(filename):
    file_md5 = hashlib.md5()
    with open(filename, 'rb') as fp:
        while chunk := fp.read(8192):
            file_md5.update(chunk)
    return str(file_md5.hexdigest())


class Mirror:

    def __init__(self, lossless: Union[Path, str], lossy: Union[Path, str]):
        self.lossless = lossless if isinstance(lossless, Path) else Path(lossless)
        self.lossy = lossy if isinstance(lossy, Path) else Path(lossy)

    def lossless_analyse(self, path, name, ext):
        lossless = self.lossless / path / (name + ext)
        lossy = self.lossy / path / f"{name}.m4a"

        fmtime = os.path.getmtime(lossless)
        fpath = path + ("\\" if path else "") + name + ext
        try:
            flac = Music.get(Music.path == fpath)
        except Music.DoesNotExist:
            # 先创建，但是等转码完成再添加写 md5 等
            flac = Music(path=fpath)
            flac.save()
            self.lossy_need.put_nowait({
                "lossless": lossless,
                "m4a": lossy,
                "col": flac,
                "md5": get_md5(lossless),
                "mtime": fmtime
            })
            return

        if fmtime != flac.mtime:
            fmd5 = get_md5(lossless)
            if fmd5 != flac.md5:
                self.lossy_need.put_nowait({
                    "lossless": lossless,
                    "m4a": lossy,
                    "col": flac,
                    "md5": fmd5,
                    "mtime": fmtime
                })
            else:
                flac.mtime = fmtime
                flac.save()

    def lossy_analyse(self, path, filename):
        fr = self.lossless / path / filename
        to = self.lossy / path / filename

        fmtime = os.path.getmtime(fr)
        fpath = path + ('\\' if path else '') + filename
        try:
            lossy = Music.get(Music.path == fpath)
        except Music.DoesNotExist:
            lossy = Music(path=fpath)
            lossy.save()
            self.copy_need.append({
                "from": fr,
                "to": to,
                "col": lossy,
                "md5": get_md5(fr),
                "mtime": fmtime
            })
            return

        if fmtime != lossy.mtime:
            fmd5 = get_md5(fr)
            if fmd5 != lossy.md5:
                self.copy_need.append({
                    "from": fr,
                    "to": to,
                    "col": lossy,
                    "md5": fmd5,
                    "mtime": fmtime
                })
            else:
                lossy.mtime = fmtime
                lossy.save()

    def analyse(self):
        self.lossy_need = asyncio.Queue()
        self.copy_need = []
        self.del_need = []

        for root, _, files in os.walk(self.lossless, topdown=False):
            if root.startswith(str(self.lossless) + "\\"):
                path = root.replace(str(self.lossless) + "\\", "", 1)
            elif root.startswith(str(self.lossless)):
                path = root.replace(str(self.lossless), "", 1)

            for f in files:
                name, ext = os.path.splitext(f)
                if ext in ['.flac', '.alac']:
                    self.lossless_analyse(path, name, ext)
                elif ext in ['.mp3', '.m4a']:
                    self.lossy_analyse(path, f)

        for col in Music.select():
            if not os.path.exists(str(self.lossless / col.path)):
                self.del_need.append((self.lossy / col.path, col))

    def copy_and_del(self):
        con = get_console()
        print("开始复制和删除")
        with con.status("testing") as status:
            al = len(self.copy_need)
            for num, file in enumerate(self.copy_need, 1):
                os.makedirs(str(file["to"].parent), exist_ok=True)
                status.update(f"\r正在[bold green]复制[default]{num}/{al}: {file['to']}")
                #print(f"正在复制{num}/{al}: {file['to']}")
                copyfile(file['from'], file['to'])
                file['col'].mtime = file['mtime']
                file['col'].md5 = file['md5']
                file['col'].save()

            al = len(self.del_need)
            for num, (file, col) in enumerate(self.del_need, 1):
                status.update(f"\r正在[bold red]删除[default]{num}/{al}: {file}")
                #print(f"正在删除{num}/{al}: {file}")
                if os.path.exists(file):
                    os.remove(file)
                col.delete_instance()
        
        print("复制和删除完成")

        # 删除空文件夹
        for root, _, _ in os.walk(self.lossy, topdown=False):
            if not os.listdir(root):
                os.removedirs(root)

    async def transfer(self, num):
        while True:
            data = await self.lossy_need.get()
            lossless_path, lossy_path = data['lossless'], data['m4a']
            #print(f"{total-self.lossy_need.qsize()}/{total}|{name}正在处理：{lossless_path.stem}")
            bar = self.progress.add_task((f"[{self.all_transfer-self.lossy_need.qsize()}/"
                                          f"{self.all_transfer}]{lossless_path.stem}"),
                                         total=100)
            os.makedirs(str(lossy_path.parent), exist_ok=True)
            cmd = [
                "qaac\qaac64", "-V", "127", "--threading", "-o",
                str(lossy_path), "--copy-artwork",
                str(lossless_path)
            ]

            shell = await asyncio.create_subprocess_exec(*cmd,
                                                         stdout=asyncio.subprocess.PIPE,
                                                         stderr=asyncio.subprocess.PIPE)

            try:
                while line := await shell.stderr.readuntil(b"\r"):
                    line = line.decode('UTF-8')
                    if line.startswith("["):
                        time = float(line[1:].split("]", 1)[0][:-1])
                        self.progress.update(bar, completed=time)
            except asyncio.IncompleteReadError:
                ...

            await shell.wait()

            if shell.returncode != 0: raise Exception

            data["col"].md5 = data["md5"]
            data["col"].mtime = data["mtime"]
            data["col"].save()

            self.progress.remove_task(bar)
            self.lossy_need.task_done()

    async def control(self):
        print("开始分析")
        self.analyse()

        astr = "分析完成"
        if qlen := self.lossy_need.qsize():
            astr += f"，有{qlen}个需要压缩"
        if qlen := len(self.copy_need):
            astr += f"，有{qlen}个需要复制"
        if qlen := len(self.del_need):
            astr += f"，有{qlen}个需要删除"
        print(astr)

        if astr == "分析完成":
            print("没有什么需要更新的哦")
            return

        # return
        style = [
            TextColumn("[progress.description]{task.description}", table_column=Column(ratio=4)),
            BarColumn(bar_width=None, table_column=Column(ratio=5)),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%",
                       table_column=Column(ratio=1))
        ]
        self.all_transfer = self.lossy_need.qsize()
        if self.all_transfer:
            print("开始压缩")
        with Progress(*style, expand=True) as progress:
            self.progress = progress
            # 因为 qaac 的 threading 只支持双核（没想到吧

            tasks = []
            for i in range(int(cpu_count() / 2)):
                task = asyncio.create_task(self.transfer(i))
                tasks.append(task)

            await self.lossy_need.join()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.all_transfer:
            print("压缩完成")
        self.copy_and_del()

lossless_folder = "lossless"
lossy_folder = "lossy"

m = Mirror(lossless_folder, lossy_folder)
asyncio.run(m.control())