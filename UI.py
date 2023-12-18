from importer import *
from tkinter.font import Font
from typing import Tuple
import threading
from tkinter import (
    END,
    INSERT,
    VERTICAL,
    X,
    Button,
    Label,
    PanedWindow,
    Text,
    Tk,
    Checkbutton,
    BooleanVar,
    Frame,
    messagebox,
    ttk,
    filedialog,
    LEFT,
    RIGHT,
)
from pathlib import Path
from catppuccin import Flavour
from dataclasses import dataclass, field
import argparse


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
        # Subscribe to events
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
        container = PanedWindow(
            self.main_window, background=self.color_scheme.background, orient=VERTICAL
        )
        container.pack(padx=30, pady=30, fill=X, expand=True)
        self.build_directory_selector_gui(container)
        self.build_checkboxes(container)
        self.build_info_panel(container)
        self.build_start_button_row(container)
        self.build_progress_indicator(container)

    # Builds the starting GUI
    def build_directory_selector_gui(self, container: PanedWindow):
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
    def build_checkboxes(self, container: PanedWindow):
        chckbox_panel = Frame(
            container,
            relief="groove",
            background=self.color_scheme.background,
        )
        chckbox_panel.pack()
        chckbox_height = 2
        # Add padding for better UX
        chckbox_padder = Label(
            chckbox_panel,
            height=chckbox_height,
            width=70,
            background=self.color_scheme.background,
        )
        chckbox_padder.pack(side=RIGHT, expand=True, fill=X)
        # Checkbox to specify recursivity
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
        # Checkbox to specify whether to overwrite existing files
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
    # Displays messages generated by the program. Use insert_warn_err to add text to it
    def build_info_panel(self, container: PanedWindow):
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

    def build_start_button_row(self, container: PanedWindow):
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
        # Label where the currently copied file is displayed
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

    def build_progress_indicator(self, container: PanedWindow):
        self.num_files = 0
        self.progress_num = 0
        progress_panel = Frame(
            container, background=self.color_scheme.background, relief="groove"
        )
        # Progressbar
        self.progressbar = ttk.Progressbar(
            progress_panel,
            orient="horizontal",
            length=200,
            mode="determinate",
        )
        self.progressbar.pack(side=LEFT)
        # Label for progress percentage
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
            self.progress_num = 0
            # Start the importer on a different thread to avoid the GUI freezing
            self.importer_thread = threading.Thread(
                target=self.importer.Import, args=(self.options,)
            )
            self.importer_thread.start()

    # The standardised way to generate a directory selector
    def dir_gui(
        self, container: PanedWindow, label_text: str
    ) -> Tuple[Button, Text, Label]:
        dir_height = 10
        # Container for the widgets
        dir_panel = Frame(
            container,
            relief="groove",
            background=self.color_scheme.background,
            height=dir_height,
        )
        dir_panel.pack(expand=True)
        # Label explaining which directory the panel belongs to
        dir_label = Label(
            dir_panel,
            text=label_text,
            background=self.color_scheme.background,
            foreground=self.color_scheme.text_color,
            font=self.label_font,
            width=len(label_text),
        )
        # Text input for the source directory
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
        # Label that displays an X when the provided directory is invalid
        dir_err = Label(
            dir_panel,
            background=self.color_scheme.background,
            font=self.label_font,
            foreground=self.color_scheme.text_color,
            width=3,
        )
        dir_err.pack(side=LEFT, expand=False)
        # Button used to open a directory selector preset
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

    # The method used when pressing select next to the source directory specifier
    def select_src_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=self.options.source,
            title="Source Directory",
            mustexist=True,
        )
        if len(tmp.strip()) > 0:
            self.set_src_dir(tmp)

    # Method used to set the source directory from code
    def set_src_dir(self, dir: str):
        self.options.source = dir
        self.src_txt.delete("1.0", END)
        self.src_txt.insert(INSERT, self.options.source)

    # The method used when pressing select next to the destination directory specifier
    def select_dst_dir(self):
        tmp = filedialog.askdirectory(
            initialdir=self.options.destination,
            title="Destination Directory",
            mustexist=True,
        )
        if len(tmp.strip()):
            self.set_dst_dir(tmp)

    # Method used to set the destination directory from code
    def set_dst_dir(self, dir: str):
        self.options.source = dir
        self.dst_txt.delete("1.0", END)
        self.dst_txt.insert(INSERT, self.options.source)

    def new_copied(self, *args, **kwds):
        self.current_file.configure(
            text=f"Moving: '...{args[0][0][len(self.options.source):]}'"
        )

    # Method called when the importer encounters an issue
    def copy_error(self, *args, **kwds):
        self.insert_warn_err(f"{args[0][0]} {args[0][1]}\n")

    def on_error(self, *args, **kwds):
        self.insert_warn_err(f"{args[0][0]}\n")

    def on_warning(self, *args, **kwds):
        self.insert_warn_err(f"{args[1]['args'][0]}\n")

    # Method called by the importer a file has been copied
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

    # Method called when the importer has found the files to be imported
    def found_files(self, *args, **kwds):
        self.num_files = len(args[0][0])

    # Method called when the importer has finished
    def on_completion(self, *args, **kwds):
        self.start_button.configure(state="normal")
        self.insert_warn_err(
            f"Done!\n{self.progress_num} out of {self.num_files} were moved.\n"
        )
        self.progress_num = 0

    # Method used to modify (insert into) the text panel displaying the importer messages
    def insert_warn_err(self, text: str):
        self.warn_err.configure(state="normal")
        self.warn_err.insert(INSERT, text)
        self.warn_err.configure(state="disabled")
        self.warn_err.see(END)


if __name__ == "__main__":
    main()
