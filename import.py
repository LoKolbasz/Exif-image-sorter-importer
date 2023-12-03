#!/usr/bin/python

import argparse

# from subprocess import call
# import timeit
import os
from pathlib import Path
from tkinter import BooleanVar, Checkbutton, font
from tkinter.font import Font
from typing import Tuple
from more_itertools import grouper
from datetime import datetime
import shutil
import concurrent.futures
from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError
from dataclasses import dataclass, field

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
        ) -> None:
            self.src = src
            self.dst = dst
            self.events = events
            self.new_copied_event = new_copied_event
            self.copy_failed_event = copy_failed_event

        def Move(self, force):
            newname = self.dst
            if force:
                newname = os.path.join(self.dst, os.path.basename(self.src))
            try:
                self.new_copied_event.__call__(self.src, newname)
                shutil.move(self.src, newname)
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

        def initExif(src, dst, events):
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
            Importer.FromTo.initExif(
                img, dst, self.events, self.new_copied_event, self.copy_failed_event
            ).Move(force)

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
        except NotFoundException:
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

    def Import(self, options: Options):
        self.events.__call__(1, "Starting import")
        self.importImages(
            files=self.GetFiles(src=options.source, isRecursive=options.recursive),
            destination=options.destination,
            force=options.force_overwrite,
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
            self.main_window, background=self.color_scheme.background
        )
        container.pack(padx=30, pady=30, fill=X, expand=True)

        # Input Fields

        # Source Directory
        (src_btn, self.src_txt, self.src_err) = self.dir_gui(
            container, "Source Directory"
        )
        src_btn.configure(command=self.select_src_dir)

        # Target directory
        (dst_btn, self.dst_txt, self.dst_err) = self.dir_gui(
            container, "Target Directory"
        )
        dst_btn.configure(command=self.select_dst_dir)

        # Checkboxes for the bool options
        chckbox_panel = PanedWindow(
            container,
            orient=HORIZONTAL,
            borderwidth=2,
            relief="groove",
            background=self.color_scheme.background,
        )
        chckbox_panel.pack()
        chckbox_height = 2
        chckbox_padder = Label(
            chckbox_panel,
            height=chckbox_height,
            width=100,
            background=self.color_scheme.background,
        )
        chckbox_panel.add(chckbox_padder)
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
        )
        chckbox_panel.add(recursive_chckbx)
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
        )
        chckbox_panel.add(force_chckbx)

        # Start button
        # Initiates the verification of the inputs and starts the sorting
        start_button_panel = PanedWindow(
            container,
            orient=HORIZONTAL,
            borderwidth=2,
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
        )
        # Infopanel
        # This is the widget that dispalys the currently copied source file, its destination, and errors encountered during the moving process
        info = PanedWindow(
            start_button_panel,
            orient=VERTICAL,
            relief="groove",
            background=self.color_scheme.background,
        )
        self.warn_err = Text(
            info,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.text_font,
        )
        info.add(self.warn_err)
        self.current_file = Label(
            info,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.label_font,
            height=2,
        )
        info.add(self.current_file)
        start_button_panel.add(info)
        start_button_panel.add(self.start_button)

    # Ask for confirmation of closing
    def on_closing(self):
        if messagebox.askokcancel(
            "Exit",
            "Are you sure, that you want to exit the application?\nThis will stop the sorting and leave already sorted files in their respective directories",
        ):
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
            self.options.recursive = self.recusrsive.get()
            self.options.force_overwrite = self.force.get()
            self.importer.Import(self.options)

    # The standardised way to generate a directory selector
    def dir_gui(
        self, container: PanedWindow, label_text: str
    ) -> Tuple[Button, Text, Label]:
        dir_height = 30
        dir_panel = PanedWindow(
            container,
            orient=HORIZONTAL,
            borderwidth=2,
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
        )
        dir_panel.add(dir_label)
        dir_panel.add(ttk.Separator(dir_panel))
        current_dir = Path.home()
        dir_selected = Text(
            dir_panel,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.text_font,
        )
        dir_selected.insert(INSERT, str(current_dir))
        dir_panel.add(dir_selected)
        dir_err = Label(
            dir_panel,
            background=self.color_scheme.background,
            font=self.label_font,
            foreground=self.color_scheme.text_color,
        )
        dir_panel.add(dir_err)
        dir_button = Button(
            dir_panel,
            text="Select",
            background=self.color_scheme.button_released,
            foreground=self.color_scheme.text_color,
            activebackground=self.color_scheme.button_hover,
            activeforeground=self.color_scheme.text_color,
            font=self.label_font,
        )
        dir_panel.add(dir_button)
        return (dir_button, dir_selected, dir_err)

    def select_src_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=str(Path.home()),
            title="Source Directory",
            mustexist=True,
        )
        self.set_src_dir(tmp)

    def set_src_dir(self, dir: str):
        self.options.source = dir
        self.src_txt.delete("1.0", END)
        self.src_txt.insert(INSERT, self.options.source)

    def select_dst_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=str(Path.home()),
            title="Destination Directory",
            mustexist=True,
        )
        self.set_dst_dir(tmp)

    def set_dst_dir(self, dir: str):
        self.options.source = dir
        self.dst_txt.delete("1.0", END)
        self.dst_txt.insert(INSERT, self.options.source)

    def new_copied(self, *args, **kwds):
        self.current_file.delete("1.0", END)
        self.current_file.insert("1.0", f"{args[0]} is being copied to: {args[1]}")

    def copy_error(self, *args, **kwds):
        self.warn_err.insert("1.0", f"{args[0]} {args[1]}")


if __name__ == "__main__":
    main()
