#!/usr/bin/python

import argparse

# from subprocess import call
# import timeit
import os
from pathlib import Path
from select import select
from tkinter import (
    BOTTOM,
    E,
    LEFT,
    RIGHT,
    TOP,
    W,
    Y,
    BooleanVar,
    Checkbutton,
    Frame,
    IntVar,
    Toplevel,
    font,
)
from tkinter.font import Font
from typing import Tuple
from more_itertools import grouper
from datetime import datetime
import shutil
import concurrent.futures
from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
from dataclasses import dataclass, field
import threading

from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    INSERT,
    VERTICAL,
    X,
    Button,
    Label,
    PanedWindow,
    Text,
    Tk,
    messagebox,
    ttk,
    filedialog,
)
from catppuccin import Flavour


def main():
    args = GetArgs()
    imp = Importer()
    if args.gui:
        if args.src is not None or args.src is not None:
            print(
                "\033[1;31m[ERROR]: \033[1;0mEither --src and --dst or --gui must be specified. Not both!"
            )
            return
        gui = GUI(imp)
    elif args.src is not None and args.dst is not None:
        src = args.src
        dst = args.dst

        print(
            f"\033[1;31mWARNING\033[1;33m this scrip assumes, that \033[1;31mALL\033[1;33m files in the \033[1;34m{src}\033[1;33m folder are images\033[1;0m"
        )
        print(
            f"The source directory: \033[1;34m{src}\n\033[1;0mThe destination directory: \033[1;34m{dst}\033[1;0m"
        )
        imp.events.__isub__(Msg.Print, 1)
        imp.events.__isub__(Msg.PrintLvl2, 2)
        imp.events.__isub__(Msg.PrintLvl3, 3)
        imp.Import(
            Options(
                source=src, destination=dst, recursive=args.r, force_overwrite=args.f
            )
        )
        print("The process has exited.\nPress \033[1;33mEnter\033[1;0m to continue")
        input()
    else:
        print(
            "\033[1;31m[ERROR]: \033[1;0mEither --src and --dst or --gui must be specified."
        )


def GetArgs():
    parser = argparse.ArgumentParser(
        description="Application to import images into separet directories based on their creation date."
    )
    parser.add_argument(
        "-s",
        "--src",
        type=str,
        help="The directory where the images are located.",
        required=False,
        default=None,
    )
    parser.add_argument(
        "-d",
        "--dst",
        type=str,
        help="The directory where the images are to be placed.",
        required=False,
        default=None,
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


# A collection of functions used to print multiple levels of logging data
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


# A dataclass to avoid help achieve a consistent colorScheme across widgets
# Warning: Do not use multiple inheritence with this as it is using slots and may break things
@dataclass(frozen=True, slots=True)
class ColorSchemeHex:
    background: str
    text_color: str
    button_pressed: str
    button_hover: str
    button_released: str
    error: str
    warning: str


# A Graphical User Interface for the importer program
@dataclass
class GUI(object):
    flavour: Flavour
    main_window: Tk
    importer: Importer
    options: Options
    color_scheme: ColorSchemeHex

    def __init__(self, imp: Importer):
        self.importer_thread = threading.Thread()
        self.counter_lock = threading.Lock()
        self.main_window = Tk()
        self.options = Options(str(Path.home()), str(Path.home()))
        self.label_font = Font(size=11)
        self.text_font = Font(size=11)
        self.importer = imp
        self.flavour = Flavour.mocha()
        self.recusrsive = BooleanVar()
        self.force = BooleanVar()
        self.color_scheme = ColorSchemeHex(
            f"#{self.flavour.base.hex}",
            f"#{self.flavour.text.hex}",
            f"#{self.flavour.mantle.hex}",
            f"#{self.flavour.overlay0.hex}",
            f"#{self.flavour.surface0.hex}",
            f"#{self.flavour.red.hex}",
            f"#{self.flavour.yellow.hex}",
        )
        self.init_gui()
        self.importer.new_copied_event.__isub__(self.new_copied)
        self.importer.copy_failed_event.__isub__(self.copy_error)
        self.importer.copy_done_event.__isub__(self.copy_done)
        self.importer.collected_files_event.__isub__(self.found_files)
        self.importer.completed_event.__isub__(self.on_completion)
        # self.importer.events.__isub__(self.on_warning, 2)
        # self.importer.events.__isub__(self.on_error, 3)
        self.main_window.mainloop()

    def init_gui(self):
        self.main_window.title("File sorter")
        self.main_window.geometry("800x600")
        self.main_window.config(
            width=800, height=600, background=f"#{self.flavour.base.hex}"
        )
        self.main_window.pack_propagate()
        self.main_window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.build_directory_selector_gui()

    # Builds the starting GUI
    def build_directory_selector_gui(self):
        container = PanedWindow(
            self.main_window, background=self.color_scheme.background, orient=VERTICAL
        )
        container.pack(padx=30, pady=30, fill=X, expand=True)

        # Input Fields

        # Source Directory
        (src_btn, self.src_txt, self.src_err) = self.dir_gui(
            container, "Source Directory:"
        )
        src_btn.configure(command=self.select_src_dir)

        # Target directory
        (dst_btn, self.dst_txt, self.dst_err) = self.dir_gui(
            container, "Target Directory:"
        )
        dst_btn.configure(command=self.select_dst_dir)

        # Checkboxes for the bool options
        chckbox_panel = Frame(
            container,
            # borderwidth=2,
            relief="groove",
            background=self.color_scheme.background,
        )
        chckbox_panel.pack()
        chckbox_height = 2
        chckbox_padder = Label(
            chckbox_panel,
            height=chckbox_height,
            width=70,
            background=self.color_scheme.background,
        )
        chckbox_padder.pack(side=RIGHT, expand=True, fill=X)
        recursive_chckbx = Checkbutton(
            chckbox_panel,
            text="Recursive",
            onvalue=True,
            offvalue=False,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            height=chckbox_height,
            font=self.label_font,
            variable=self.recusrsive,
            width=len("Recursive"),
            borderwidth=0,
        )
        recursive_chckbx.pack(side=LEFT)
        force_chckbx = Checkbutton(
            chckbox_panel,
            text="Force overwrite",
            onvalue=True,
            offvalue=False,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            height=chckbox_height,
            font=self.label_font,
            variable=self.force,
            width=len("Force overwrite"),
            borderwidth=0,
        )
        force_chckbx.pack(side=LEFT)
        # Infopanel
        # This is the widget that dispalys the currently copied source file, its destination, and errors encountered during the moving process
        warn_height = 15
        info = Frame(
            container,
            relief="groove",
            background=self.color_scheme.background,
        )
        self.warn_err = Text(
            info,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.text_font,
            height=warn_height,
            width=200,
        )
        self.warn_err.pack()
        info.pack()
        # Start button
        # Initiates the verification of the inputs and starts the sorting
        start_button_panel = Frame(
            container,
            relief="groove",
            background=self.color_scheme.background,
        )
        start_button_panel.pack()
        self.start_button = Button(
            start_button_panel,
            command=self.start_program,
            text="Start sorting",
            background=self.color_scheme.button_released,
            foreground=self.color_scheme.text_color,
            activebackground=self.color_scheme.button_hover,
            activeforeground=self.color_scheme.text_color,
            font=self.label_font,
            width=len("Start sorting"),
            height=1,
        )
        self.start_button.pack(side=RIGHT)
        self.current_file = Label(
            start_button_panel,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.label_font,
            height=1,
            width=200 - len("Start sorting"),
        )
        self.current_file.pack(side=RIGHT)
        start_button_panel.pack()
        self.num_files = value = 0
        self.progress_num = 0
        # Progress indicator
        progress_panel = Frame(
            container, background=self.color_scheme.background, relief="groove"
        )
        self.progressbar = ttk.Progressbar(
            progress_panel,
            orient="horizontal",
            length=200,
            mode="determinate",
        )
        self.progressbar.pack(side=LEFT)
        self.progress_percentage = Label(
            progress_panel,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.label_font,
            text="0%",
            width=4,
        )
        self.progress_percentage.pack(side=LEFT)
        progress_panel.pack()

    # Ask for confirmation of closing
    def on_closing(self):
        if messagebox.askokcancel(
            "Exit",
            "Are you sure, that you want to exit the application?\nThis will stop the sorting and leave already sorted files in their respective directories",
        ):
            if self.importer_thread.is_alive():
                self.importer.cancel()
                self.importer_thread.join()
            self.main_window.destroy()

    # The function to call in order  to start the execution of the sorter
    def start_program(self):
        ready = True
        # Stripping is necessary otherwise the path will not be correct. This is due to leading and trailing the whitespace in the text input
        self.options.source = self.src_txt.get("1.0", END).strip()
        if not Path(self.options.source).is_dir():
            self.src_err.configure(text="❌", foreground=self.color_scheme.error)
            ready = False
        else:
            self.src_err.configure(text="", foreground=self.color_scheme.text_color)
        self.options.destination = self.dst_txt.get("1.0", END).strip()
        if not Path(self.options.destination).is_dir():
            self.dst_err.configure(text="❌", foreground=self.color_scheme.error)
            ready = False
        else:
            self.dst_err.configure(text="", foreground=self.color_scheme.text_color)
        if ready:
            self.start_button.configure(state="disabled")
            self.options.recursive = self.recusrsive.get()
            self.options.force_overwrite = self.force.get()
            print(self.options)
            self.progress_num = 0
            self.importer_thread = threading.Thread(
                target=self.importer.Import, args=(self.options,)
            )
            self.importer_thread.start()

    # The standardised way to generate a directory selector
    def dir_gui(
        self, container: PanedWindow, label_text: str
    ) -> Tuple[Button, Text, Label]:
        dir_height = 10
        dir_panel = Frame(
            container,
            relief="groove",
            background=self.color_scheme.background,
            height=dir_height,
        )
        dir_panel.pack(expand=True)
        dir_label = Label(
            dir_panel,
            text=label_text,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.label_font,
            width=len(label_text),
        )
        dir_label.pack(side=LEFT, expand=False)
        current_dir = Path.home()
        dir_selected = Text(
            dir_panel,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.text_font,
            height=1,
            wrap="none",
            width=60,
        )
        dir_selected.insert(INSERT, str(current_dir))
        dir_selected.pack(side=LEFT, expand=True, fill=X)
        dir_err = Label(
            dir_panel,
            background=self.color_scheme.background,
            font=self.label_font,
            foreground=self.color_scheme.text_color,
            width=3,
        )
        dir_err.pack(side=LEFT, expand=False)
        dir_button = Button(
            dir_panel,
            text="Select",
            background=self.color_scheme.button_released,
            foreground=self.color_scheme.text_color,
            activebackground=self.color_scheme.button_hover,
            activeforeground=self.color_scheme.text_color,
            font=self.label_font,
            borderwidth=0,
            height=1,
        )
        dir_button.pack(side=LEFT, expand=False)
        return (dir_button, dir_selected, dir_err)

    def select_src_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=self.options.source,
            title="Source Directory",
            mustexist=True,
        )
        if len(tmp.strip()) > 0:
            self.set_src_dir(tmp)

    def set_src_dir(self, dir: str):
        self.options.source = dir
        self.src_txt.delete("1.0", END)
        self.src_txt.insert(INSERT, self.options.source)

    def select_dst_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=self.options.destination,
            title="Destination Directory",
            mustexist=True,
        )
        if len(tmp.strip()):
            self.set_dst_dir(tmp)

    def set_dst_dir(self, dir: str):
        self.options.source = dir
        self.dst_txt.delete("1.0", END)
        self.dst_txt.insert(INSERT, self.options.source)

    def new_copied(self, *args, **kwds):
        self.current_file.configure(
            text=f"Moving: '...{args[0][0][len(self.options.source):]}'"
        )

    def copy_error(self, *args, **kwds):
        self.insert_warn_err(f"\n{args[0][0]} {args[0][1]}")

    def on_error(self, *args, **kwds):
        self.insert_warn_err(f"\n{args[0][0]}")

    def on_warning(self, *args, **kwds):
        self.insert_warn_err(f"\n{args[1]['args'][0]}\n")

    def copy_done(self, *args, **kwds):
        if self.num_files == 0:
            return
        with self.counter_lock:
            self.progress_num += 1
            percentage = 100 * self.progress_num / self.num_files
            self.progressbar["value"] = percentage
        self.progress_percentage.configure(
            text=f"{round(100 * self.progress_num / self.num_files)}%"
        )

    def found_files(self, *args, **kwds):
        self.num_files = len(args[0][0])

    def on_completion(self, *args, **kwds):
        self.start_button.configure(state="normal")
        self.insert_warn_err(
            f"Done!\n{self.progress_num} out of {self.num_files} were moved.\n"
        )
        self.progress_num = 0

    def insert_warn_err(self, text: str):
        self.warn_err.configure(state="normal")
        self.warn_err.insert(INSERT, text)
        self.warn_err.configure(state="disabled")
        self.warn_err.see(END)


if __name__ == "__main__":
    main()
