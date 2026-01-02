#!/usr/bin/env python3
import curses
import os
import time
import configparser
from copy import deepcopy

CONFIG_PATH = os.path.expanduser("~/.cleditrc")

DEFAULT_CONFIG = {
    "editor": {
        "tab_size": "4",
        "autosave": "false",
        "show_line_numbers": "true"
    }
}

CTRL = lambda x: ord(x) & 0x1f

MENU_ITEMS = ["File", "Edit", "Help"]

class Editor:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.rows, self.cols = stdscr.getmaxyx()

        self.load_config()

        self.filename = None
        self.lines = [""]
        self.cx = self.cy = 0
        self.scroll = 0

        self.undo_stack = []
        self.redo_stack = []

        self.modified = False
        self.menu_mode = False
        self.active_menu = 0
        self.clipboard = ""
        self.running = True

    # ───────────────── CONFIG ─────────────────

    def load_config(self):
        if not os.path.exists(CONFIG_PATH):
            self.create_default_config()

        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_PATH)

        self.tab_size = int(self.config["editor"].get("tab_size", 4))
        self.autosave = self.config["editor"].getboolean("autosave")
        self.show_line_numbers = self.config["editor"].getboolean("show_line_numbers")

    def create_default_config(self):
        cfg = configparser.ConfigParser()
        cfg.read_dict(DEFAULT_CONFIG)
        with open(CONFIG_PATH, "w") as f:
            cfg.write(f)

    # ───────────────── UNDO / REDO ─────────────────

    def snapshot(self):
        self.undo_stack.append((deepcopy(self.lines), self.cx, self.cy))
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append((deepcopy(self.lines), self.cx, self.cy))
        self.lines, self.cx, self.cy = self.undo_stack.pop()

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append((deepcopy(self.lines), self.cx, self.cy))
        self.lines, self.cx, self.cy = self.redo_stack.pop()

    # ───────────────── DRAWING ─────────────────

    def draw(self):
        self.stdscr.erase()
        self.draw_menu()
        self.draw_text()
        self.draw_status()
        self.stdscr.refresh()

    def draw_menu(self):
        self.stdscr.attron(curses.A_REVERSE)
        x = 1
        for i, m in enumerate(MENU_ITEMS):
            if self.menu_mode and i == self.active_menu:
                self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(0, x, f" {m} ")
            self.stdscr.attroff(curses.A_BOLD)
            x += len(m) + 2
        self.stdscr.addstr(0, x, " " * (self.cols - x))
        self.stdscr.attroff(curses.A_REVERSE)

    def draw_text(self):
        h = self.rows - 2
        for i in range(h):
            idx = i + self.scroll
            if idx >= len(self.lines):
                break

            line = self.lines[idx]
            prefix = ""
            if self.show_line_numbers:
                prefix = f"{idx+1:4} "

            self.stdscr.addstr(i + 1, 0, (prefix + line)[:self.cols - 1])

        cy = self.cy - self.scroll + 1
        cx = self.cx + (5 if self.show_line_numbers else 0)
        if 1 <= cy < self.rows - 1:
            self.stdscr.move(cy, cx)

    def draw_status(self):
        name = self.filename if self.filename else "Untitled"
        mod = "*" if self.modified else ""
        msg = f"{name}{mod} | Ctrl+S Save | Ctrl+Z Undo | Ctrl+Y Redo | Ctrl+L Menu"
        self.stdscr.attron(curses.A_REVERSE)
        self.stdscr.addstr(self.rows - 1, 0, msg.ljust(self.cols - 1))
        self.stdscr.attroff(curses.A_REVERSE)

    # ───────────────── FILE OPS ─────────────────

    def save(self):
        if not self.filename:
            self.prompt_save_as()
            return
        with open(self.filename, "w") as f:
            f.write("\n".join(self.lines))
        self.modified = False

    def prompt_save_as(self):
        curses.echo()
        self.stdscr.addstr(self.rows - 1, 0, "Save as: ".ljust(self.cols))
        name = self.stdscr.getstr(self.rows - 1, 9).decode()
        curses.noecho()
        if name:
            self.filename = name
            self.save()

    # ───────────────── INPUT HANDLER ─────────────────

    def handle_input(self, ch):
        if self.menu_mode:
            self.handle_menu(ch)
            return

        if ch == CTRL('q'):
            self.running = False
        elif ch == CTRL('s'):
            self.save()
        elif ch == CTRL('z'):
            self.undo()
        elif ch == CTRL('y'):
            self.redo()
        elif ch == CTRL('l'):
            self.menu_mode = True
        elif ch == curses.KEY_LEFT:
            self.cx = max(0, self.cx - 1)
        elif ch == curses.KEY_RIGHT:
            self.cx = min(len(self.lines[self.cy]), self.cx + 1)
        elif ch == curses.KEY_UP:
            self.cy = max(0, self.cy - 1)
        elif ch == curses.KEY_DOWN:
            self.cy = min(len(self.lines) - 1, self.cy + 1)
        elif ch in (10, 13):
            self.snapshot()
            line = self.lines[self.cy]
            self.lines[self.cy] = line[:self.cx]
            self.lines.insert(self.cy + 1, line[self.cx:])
            self.cx = 0
            self.cy += 1
            self.modified = True
        elif ch in (8, 127):
            self.snapshot()
            if self.cx > 0:
                line = self.lines[self.cy]
                self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
                self.cx -= 1
            elif self.cy > 0:
                prev = self.lines[self.cy - 1]
                self.cx = len(prev)
                self.lines[self.cy - 1] += self.lines[self.cy]
                del self.lines[self.cy]
                self.cy -= 1
            self.modified = True
        elif 32 <= ch <= 126:
            self.snapshot()
            line = self.lines[self.cy]
            self.lines[self.cy] = line[:self.cx] + chr(ch) + line[self.cx:]
            self.cx += 1
            self.modified = True

    def handle_menu(self, ch):
        if ch in (27,):
            self.menu_mode = False
            return
        if ch == curses.KEY_LEFT:
            self.active_menu = (self.active_menu - 1) % len(MENU_ITEMS)
        elif ch == curses.KEY_RIGHT:
            self.active_menu = (self.active_menu + 1) % len(MENU_ITEMS)
        elif ch in (10, 13):
            if MENU_ITEMS[self.active_menu] == "File":
                self.file_menu()
            elif MENU_ITEMS[self.active_menu] == "Edit":
                self.edit_menu()
            elif MENU_ITEMS[self.active_menu] == "Help":
                self.help_menu()
            self.menu_mode = False

    def file_menu(self):
        self.stdscr.addstr(self.rows - 1, 0, "File: N-New  O-Open  S-Save  Q-Quit")
        ch = self.stdscr.getch()
        if ch in (ord('n'), ord('N')):
            self.lines = [""]
            self.filename = None
        elif ch in (ord('o'), ord('O')):
            self.prompt_open()
        elif ch in (ord('s'), ord('S')):
            self.save()
        elif ch in (ord('q'), ord('Q')):
            self.running = False

    def edit_menu(self):
        self.stdscr.addstr(self.rows - 1, 0, "Edit: Z-Undo  Y-Redo")
        ch = self.stdscr.getch()
        if ch in (ord('z'), ord('Z')):
            self.undo()
        elif ch in (ord('y'), ord('Y')):
            self.redo()

    def help_menu(self):
        self.stdscr.addstr(self.rows - 1, 0, "CLEdit - Minimal Terminal Editor")

    def prompt_open(self):
        curses.echo()
        self.stdscr.addstr(self.rows - 1, 0, "Open file: ".ljust(self.cols))
        path = self.stdscr.getstr(self.rows - 1, 11).decode()
        curses.noecho()
        if path:
            with open(path) as f:
                self.lines = f.read().splitlines()
            self.filename = path
            self.modified = False

    # ───────────────── MAIN LOOP ─────────────────

    def run(self):
        self.show_welcome()
        while self.running:
            self.draw()
            self.handle_input(self.stdscr.getch())

    def show_welcome(self):
        self.stdscr.clear()
        msg = [
            "CLEdit — Terminal Text Editor",
            "",
            "Ctrl+L : Menu",
            "Ctrl+Z / Ctrl+Y : Undo / Redo",
            "Config file: ~/.cleditrc",
            "",
            "Press any key to start..."
        ]
        for i, line in enumerate(msg):
            self.stdscr.addstr(i + 3, 5, line)
        self.stdscr.refresh()
        self.stdscr.getch()


def main(stdscr):
    curses.curs_set(1)
    stdscr.keypad(True)
    Editor(stdscr).run()


if __name__ == "__main__":
    curses.wrapper(main)
