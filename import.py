#!/usr/bin/python

import argparse

# from subprocess import call
# import timeit
import os
from more_itertools import grouper
from datetime import datetime
import shutil
import concurrent.futures
from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError


def main():
    args = GetArgs()

    src = args.src
    dst = args.dst

    print(
        f"\033[1;31mWARNING\033[1;33m this scrip assumes, that \033[1;31mALL\033[1;33m files in the \033[1;34m{src}\033[1;33m folder are images\033[1;0m"
    )
    print(
        f"The source directory: \033[1;34m{src}\n\033[1;0mThe destination directory: \033[1;34m{dst}\033[1;0m"
    )
    imp = Importer()
    imp.events.__isub__(Msg.Print, 1)
    imp.events.__isub__(Msg.PrintLvl2, 2)
    imp.events.__isub__(Msg.PrintLvl3, 3)
    imp.Import(src=src, dst=dst, isRecursive=args.r, force=args.f)
    print("The process has exited.\nPress \033[1;33mEnter\033[1;0m to continue")
    input()


def GetArgs():
    parser = argparse.ArgumentParser(
        description="Application to import images into separet directories based on their creation date."
    )
    parser.add_argument(
        "-s",
        "--src",
        type=str,
        help="The directory where the images are located.",
        required=True,
    )
    parser.add_argument(
        "-d",
        "--dst",
        type=str,
        help="The directory where the images are to be placed.",
        required=True,
    )
    parser.add_argument(
        "-r",
        action="store_true",
        help="If this option is specified the source directory is searched reqursively. It's set to false by default",
        required=False,
        default=False,
    )
    parser.add_argument(
        "-f",
        action="store_true",
        help="If this option is set files in the dst directory will be overwritten if names match. It's set to false by default",
        required=False,
        default=False,
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Starts the program with a graphical user interface (a.k.a. GUI)",
        required=False,
    )
    return parser.parse_args()


class NotFoundException(Exception):
    pass


class Importer:
    def __init__(self):
        self.events = Msges()

    class FromTo:
        def __init__(self, src, dst, events) -> None:
            self.src = src
            self.dst = dst
            self.events = events

        def Move(self, force):
            newname = self.dst
            if force:
                newname = os.path.join(self.dst, os.path.basename(self.src))
            try:
                shutil.move(self.src, newname)
            except IOError as e:
                self.events.__call__(2, str(e))
                if e.strerror == "Not a directory":
                    self.events.__call__(2, f"\33[1;31m{e}\33[1;0m")
                    return
                self.events.__call__(
                    2,
                    f'\33[1;32m"{self.dst}" directory not found.\33[1;0m Creating directory by the same name',
                )
                os.makedirs(self.dst)
                shutil.move(self.src, newname)

        def initExif(src, dst, events):
            return Importer.FromTo(
                src,
                os.path.join(
                    dst,
                    Importer.FromTo.whatType(src),
                    f"{Importer.FromTo.getExifDate(src)}/",
                ),
                events=events,
            )

        def whatType(img):
            try:
                with ExifToolHelper() as et:
                    return et.get_metadata(img)[0]["File:FileType"].lower()
            except (KeyError, ExifToolExecuteError):
                tp = img.split(".")
                if len(tp) and len(tp[-1]) < 6:
                    return tp[-1].lower()
                return "misc"

        def getTagVal(meta, tag):
            for k, v in meta[0].items():
                splat = k.split(":")
                if len(splat) > 1 and splat[1] == tag:
                    return v
            raise NotFoundException(tag + " was not found")

        def getExifDate(img):
            try:
                with ExifToolHelper() as et:
                    out = et.get_tags(
                        files=[img], tags=["DateTimeOriginal", "CreateDate"]
                    )
                    return Importer.FromTo.getTagVal(out, "DateTimeOriginal")[
                        0:10
                    ].replace(":", ".")
            except ExifToolExecuteError:
                return datetime.strftime(datetime.now(), "%Y.%m.%d")

    def moveImages(self, srcImg, dst, force):
        for img in srcImg:
            Importer.FromTo.initExif(img, dst, events=self.events).Move(force)

    def importImages(self, destination, files, force):
        if destination[-1] != "/":
            destination += "/"
        try:
            if not files:
                raise ValueError("No files selected for import")
            executor = concurrent.futures.ProcessPoolExecutor(10)
            futures = [
                executor.submit(self.moveImages, group, destination, force)
                for group in grouper(files, 5)
            ]
            concurrent.futures.wait(futures)
        except NotFoundException as e:
            return 1
        except ValueError as e:
            self.events.__call__(2, str(e))
            return 2
        return 0

    def GetFilesRecursively(self, src):
        return [
            t
            for f in [
                [os.path.join(root, f) for f in files]
                for root, dir, files in os.walk(src)
            ]
            for t in f
        ]

    def GetFilesNonRecursively(self, src):
        return [
            os.path.join(src, f)
            for f in os.listdir(src)
            if os.path.isfile(os.path.join(src, f))
        ]

    def GetFiles(self, src: str, isRecursive: bool):
        if isRecursive:
            self.events.__call__(1, "Getting files recursively")
            files = self.GetFilesRecursively(src)
        else:
            self.events.__call__(1, "Getting files non recursively")
            files = self.GetFilesNonRecursively(src)
        self.events.__call__(
            1, f"Searching for files has finished. Found {len(files)} files."
        )
        return files

    def Import(
        self, src: str, dst: str, isRecursive: bool = False, force: bool = False
    ):
        self.events.__call__(1, "Starting import")
        self.importImages(
            files=self.GetFiles(src=src, isRecursive=isRecursive),
            destination=dst,
            force=force,
        )
        self.events.__call__(1, "Finished")


class MsgEvent(object):
    def __init__(self):
        self.eventSubs = []

    def __isub__(self, Ehandler):
        self.eventSubs.append(Ehandler)

    def __iunsub__(self, Ehandler):
        self.eventSubs.remove(Ehandler)

    def __call__(self, *args, **kwds):
        for Ehandler in self.eventSubs:
            Ehandler(args, kwds)


class Msg:
    def __init__(self, *args):
        self.text = []
        self.args = args[0][1]["args"]
        for a in self.args:
            self.text.append(a)

    def display(self):
        for t in self.text:
            print(t)

    def Print(*args, **kwds):
        m = Msg(args)
        for i in range(len(m.text)):
            m.text[i] = f"\033[1;32m[INFO]: {m.text[i]}\033[1;0m"  # 32 green
        m.display()

    def PrintLvl2(*args, **kwds):
        m = Msg(args)
        for i in range(len(m.text)):
            m.text[i] = f"\033[1;33m[WARNING]: {m.text[i]}\033[1;0m"  # 33 yellow
        m.display()

    def PrintLvl3(*args, **kwds):
        m = Msg(args)
        for i in range(len(m.text)):
            m.text[i] = f"\033[1;31m[ERROR]: {m.text[i]}\033[1;0m"  # 31 red
        m.display()


class Msges(MsgEvent):
    def __init__(self, lvls: int = 3) -> None:
        self.lvls = [MsgEvent()]
        for i in range(0, lvls - 1):
            self.lvls.append(MsgEvent())

    def __isub__(self, Ehandler, lvl=1):
        if lvl < 1 or lvl > len(self.lvls):
            raise ValueError(f"There is no level with level: {lvl}")
        lvl -= 1
        self.lvls[lvl].__isub__(Ehandler)

    def __iunsub__(self, Ehandler, lvl: int = 1):
        if lvl < 1 or lvl > len(self.lvls):
            raise ValueError(f"There is no level with level: {lvl}")
        lvl -= 1
        self.lvls[lvl].__iunsub__(Ehandler)

    def __call__(self, lvl: int = 1, *args, **kwds):
        if lvl < 1 or lvl > len(self.lvls):
            raise ValueError(f"There is no level with level: {lvl}")
        lvl -= 1
        self.lvls[lvl].__call__(args=args, kwds=kwds)


if __name__ == "__main__":
    main()
