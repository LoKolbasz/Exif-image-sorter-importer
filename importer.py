#!/usr/bin/python

import os
from more_itertools import grouper
from datetime import datetime
import shutil
import concurrent.futures
from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
from dataclasses import dataclass, field


class NotFoundException(Exception):
    pass


@dataclass
class Options:
    source: str
    destination: str
    recursive: bool = field(default=False)
    force_overwrite: bool = field(default=False)


class Importer:
    def __init__(self):
        self.events = Msges()
        self.new_copied_event = MsgEvent()
        self.copy_failed_event = MsgEvent()
        self.copy_done_event = MsgEvent()
        self.collected_files_event = MsgEvent()
        self.completed_event = MsgEvent()
        self.stop = False

    dataclass(slots=True, frozen=True)

    class FromTo:
        src: str
        dst: str

        def __init__(
            self,
            src,
            dst,
            events,
            new_copied_event,
            copy_failed_event,
            copy_done_event,
            collected_files_event,
        ) -> None:
            self.src = src
            self.dst = dst
            self.events = events
            self.new_copied_event = new_copied_event
            self.copy_failed_event = copy_failed_event
            self.copy_done_event = copy_done_event
            self.collected_files_event = collected_files_event

        # Moves a file from self.src to a previously calculated self.dst.
        def Move(self, force):
            newname = self.dst
            if force:
                newname = os.path.join(self.dst, os.path.basename(self.src))
            try:
                self.new_copied_event.__call__(self.src, newname)
                shutil.move(self.src, newname)
                self.copy_done_event.__call__(self.src, newname)
            except IOError as e:
                self.events.__call__(2, str(e))
                if e.strerror == "Not a directory":
                    self.events.__call__(2, f"\33[1;31m{e}\33[1;0m")
                    self.copy_failed_event.__call__(self.dst, str(e))
                    return
                self.events.__call__(
                    2,
                    f'\33[1;32m"{self.dst}" directory not found.\33[1;0m Creating directory by the same name',
                )
                self.copy_failed_event.__call__(self.dst, "Directory not found")
                os.makedirs(self.dst)
                shutil.move(self.src, newname)

        # Initialises a FromTo instance and returns it. It is used to convert arguments to formats expected by __init__
        def initExif(
            src,
            dst,
            events,
            new_copied_event,
            copy_failed_event,
            copy_done_event,
            collected_files_event,
        ):
            return Importer.FromTo(
                src,
                os.path.join(
                    dst,
                    Importer.FromTo.whatType(src),
                    f"{Importer.FromTo.getExifDate(src)}/",
                ),
                events,
                new_copied_event,
                copy_failed_event,
                copy_done_event,
                collected_files_event,
            )

        # Gets the filetype. It is used to get the filetype directory name
        def whatType(img):
            try:
                with ExifToolHelper() as et:
                    return et.get_metadata(img)[0]["File:FileType"].lower()
            except (KeyError, ExifToolExecuteError):
                tp = img.split(".")
                if len(tp) and len(tp[-1]) < 6:
                    return tp[-1].lower()
                return "misc"

        # Gets the tag value (specified by the rag argument) of a meta exiftool metadata object
        def getTagVal(meta, tag):
            for k, v in meta[0].items():
                splat = k.split(":")
                if len(splat) > 1 and splat[1] == tag:
                    return v
            raise NotFoundException(tag + " was not found")

        # Gets the date the file was created on using exiftool. If a suitable tag is not found, the current date is returned in the YYYY.MM.DD format
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

    # Moves a collection of images to the specified directory. The new path of the files will be: destination/filetype/file creation date/ original file name
    def moveImages(self, srcImg, dst: str, force: bool):
        for img in srcImg:
            if self.stop:
                break
            Importer.FromTo.initExif(
                img,
                dst,
                self.events,
                self.new_copied_event,
                self.copy_failed_event,
                self.copy_done_event,
                self.collected_files_event,
            ).Move(force)

    # Moves a collection of images concurrently to the specified directory. The new path follows the destination/filetype/file creation data/original filename  pattern
    def importImages(self, destination: str, files: list[str], force):
        if destination[-1] != "/":
            destination += "/"
        try:
            if not files:
                raise ValueError("No files selected for import")
            # Create concurrent threads
            executor = concurrent.futures.ThreadPoolExecutor(10)
            futures = [
                executor.submit(self.moveImages, group, destination, force)
                # Divides the collection into groups of 5 (at most)
                for group in grouper(files, 5)
            ]
            concurrent.futures.wait(futures)
            # self.moveImages(files, destination, force)
        except NotFoundException:
            return 1
        except ValueError as e:
            self.events.__call__(2, str(e))
            return 2
        return 0

    # Collects the files both in the parent and in the subdirectories and returns them as a list of strings that are the paths to those files
    def GetFilesRecursively(self, src):
        return [
            t
            for f in [
                [os.path.join(root, f) for f in files]
                for root, dir, files in os.walk(src)
            ]
            for t in f
        ]

    # Collects the files in the specified directory and returns them as a collection of strings that are paths to those fles
    def GetFilesNonRecursively(self, src):
        return [
            os.path.join(src, f)
            for f in os.listdir(src)
            if os.path.isfile(os.path.join(src, f))
        ]

    # Collects the files to be processed
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
        self.collected_files_event.__call__(files)
        return files

    # Wrapper for the whole import procvess
    def Import(self, options: Options):
        self.events.__call__(1, "Starting import")
        self.stop = False
        self.importImages(
            files=self.GetFiles(src=options.source, isRecursive=options.recursive),
            destination=options.destination,
            force=options.force_overwrite,
        )
        self.events.__call__(1, "Finished")
        self.completed_event.__call__()

    # Stop the importing
    def cancel(self):
        self.stop = True


# An event that can be used to perform callbacks
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


# A collection of events used to perform callbacks for multilevel logging
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
