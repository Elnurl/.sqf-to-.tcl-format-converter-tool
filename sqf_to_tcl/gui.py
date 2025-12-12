"""Modern PyQt6 IDE-like GUI for the SQF -> TCL converter.

Run with:
    python -m sqf_to_tcl.gui

Features:
- IDE-like code editor with line numbers and syntax highlighting
- Split view for input and output
- Find/Replace functionality
- Select an input `.sqf` file or paste SQF into the editor
- Convert to TCL and preview in the output area
- Save converted TCL to a file
"""
from __future__ import annotations
import sys
import re
import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QLabel, QFileDialog, QMessageBox,
    QCheckBox, QSplitter, QFrame, QSizePolicy, QTextEdit,
    QDialog, QLineEdit, QGroupBox, QScrollArea
)
from PyQt6.QtCore import Qt, QSize, QRect, pyqtSignal
from PyQt6.QtGui import (
    QFont, QPalette, QColor, QIcon, QTextCharFormat, QSyntaxHighlighter,
    QPainter, QTextFormat, QTextCursor, QTextDocument
)

# Use absolute import so it also works when frozen as a standalone .exe
from sqf_to_tcl.converter.translator import convert_sqf_string_to_tcl, save_tcl_output


class LineNumberArea(QWidget):
    """Widget for displaying line numbers."""
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """IDE-like code editor with line numbers and syntax highlighting."""
    def __init__(self, language: str = "sqf", parent=None):
        super().__init__(parent)
        self.language = language
        self.line_number_area = LineNumberArea(self)
        
        # Font setup with zoom support
        self.base_font_size = 11
        font = QFont("Consolas", self.base_font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        
        # Editor styling
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                selection-background-color: #264f78;
            }
        """)
        
        # Line number area styling
        self.line_number_area.setStyleSheet("""
            QWidget {
                background-color: #252526;
                border-right: 1px solid #3e3e3e;
            }
        """)
        
        # Connect signals
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        
        # Set up syntax highlighting
        if language == "sqf":
            self.highlighter = SQFSyntaxHighlighter(self.document())
        elif language == "tcl":
            self.highlighter = TCLSyntaxHighlighter(self.document())
        else:
            self.highlighter = None
        
        # Initial setup
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        
    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        space = 8 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(37, 37, 38))
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(133, 133, 133))
                painter.drawText(
                    0, top, self.line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(42, 45, 46)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def get_cursor_position(self):
        """Get current line and column."""
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        return line, col
    
    def zoom_in(self):
        """Increase font size (zoom in)."""
        current_size = self.font().pointSize()
        new_size = min(current_size + 1, 24)  # Max 24pt
        font = self.font()
        font.setPointSize(new_size)
        self.setFont(font)
        return new_size
    
    def zoom_out(self):
        """Decrease font size (zoom out)."""
        current_size = self.font().pointSize()
        new_size = max(current_size - 1, 8)  # Min 8pt
        font = self.font()
        font.setPointSize(new_size)
        self.setFont(font)
        return new_size
    
    def zoom_reset(self):
        """Reset font size to default."""
        font = self.font()
        font.setPointSize(self.base_font_size)
        self.setFont(font)
        return self.base_font_size
    
    def get_zoom_percentage(self):
        """Get current zoom percentage."""
        current_size = self.font().pointSize()
        return int((current_size / self.base_font_size) * 100)


class SQFSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for SQF language."""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Keyword format
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(86, 156, 214))
        keyword_format.setFontWeight(600)
        
        # String format
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(206, 145, 120))
        
        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))
        comment_format.setFontItalic(True)
        
        # Number format
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(181, 206, 168))
        
        # Operator format
        operator_format = QTextCharFormat()
        operator_format.setForeground(QColor(212, 212, 212))
        operator_format.setFontWeight(600)
        
        # Variable format
        variable_format = QTextCharFormat()
        variable_format.setForeground(QColor(156, 220, 254))
        
        # SQF keywords
        keywords = [
            'if', 'then', 'else', 'for', 'from', 'to', 'do', 'while',
            'sleep', 'hint', 'format', 'set', 'private', 'params',
            'call', 'spawn', 'waitUntil', 'switch', 'case', 'default',
            'true', 'false', 'nil', 'and', 'or', 'not'
        ]
        
        self.rules = []
        
        # Keywords
        for keyword in keywords:
            pattern = r'\b' + keyword + r'\b'
            self.rules.append((pattern, keyword_format))
        
        # Strings (double quotes)
        self.rules.append((r'"[^"]*"', string_format))
        
        # Strings (single quotes)
        self.rules.append((r"'[^']*'", string_format))
        
        # Single-line comments
        self.rules.append((r'//.*', comment_format))
        
        # Multi-line comments
        self.comment_start = re.compile(r'/\*')
        self.comment_end = re.compile(r'\*/')
        self.comment_format = comment_format
        
        # Numbers
        self.rules.append((r'\b\d+\.?\d*\b', number_format))
        
        # Operators
        operators = [r'=', r'==', r'!=', r'<=', r'>=', r'<', r'>',
                    r'\+', r'-', r'\*', r'/', r'%', r'&&', r'\|\|']
        for op in operators:
            self.rules.append((op, operator_format))
        
        # Variables (starting with underscore)
        self.rules.append((r'\b_[a-zA-Z_][a-zA-Z0-9_]*\b', variable_format))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in re.finditer(pattern, text):
                start, end = match.span()
                self.setFormat(start, end - start, format)
        
        # Handle multi-line comments
        self.setCurrentBlockState(0)
        start_match = self.comment_start.search(text)
        if start_match:
            end_match = self.comment_end.search(text, start_match.end())
            if end_match:
                length = end_match.end() - start_match.start()
                self.setFormat(start_match.start(), length, self.comment_format)
            else:
                self.setCurrentBlockState(1)
                self.setFormat(start_match.start(), len(text) - start_match.start(), self.comment_format)
        elif self.previousBlockState() == 1:
            end_match = self.comment_end.search(text)
            if end_match:
                self.setFormat(0, end_match.end(), self.comment_format)
            else:
                self.setFormat(0, len(text), self.comment_format)
                self.setCurrentBlockState(1)


class TCLSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for TCL language."""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Keyword format
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(86, 156, 214))
        keyword_format.setFontWeight(600)
        
        # String format
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(206, 145, 120))
        
        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(106, 153, 85))
        comment_format.setFontItalic(True)
        
        # Variable format
        variable_format = QTextCharFormat()
        variable_format.setForeground(QColor(156, 220, 254))
        
        # Command format
        command_format = QTextCharFormat()
        command_format.setForeground(QColor(220, 220, 170))
        
        # TCL keywords
        keywords = [
            'if', 'else', 'elseif', 'for', 'while', 'foreach',
            'set', 'proc', 'return', 'break', 'continue',
            'puts', 'after', 'incr', 'expr'
        ]
        
        self.rules = []
        
        # Keywords
        for keyword in keywords:
            pattern = r'\b' + keyword + r'\b'
            self.rules.append((pattern, keyword_format))
        
        # Strings (double quotes)
        self.rules.append((r'"[^"]*"', string_format))
        
        # Strings (single quotes)
        self.rules.append((r"'[^']*'", string_format))
        
        # Comments
        self.rules.append((r'#.*', comment_format))
        
        # Variables ($var)
        self.rules.append((r'\$[a-zA-Z_][a-zA-Z0-9_]*', variable_format))
        
        # Commands (first word on line)
        self.rules.append((r'^\s*[a-zA-Z_][a-zA-Z0-9_]*', command_format))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            for match in re.finditer(pattern, text):
                start, end = match.span()
                self.setFormat(start, end - start, format)


class FindReplaceDialog(QDialog):
    """Find and Replace dialog."""
    def __init__(self, parent=None, editor=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find & Replace")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
            }
            QLabel {
                color: #cccccc;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Find section
        find_group = QGroupBox("Find")
        find_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        find_layout = QVBoxLayout(find_group)
        
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Enter text to find...")
        find_layout.addWidget(self.find_input)
        
        find_btn_layout = QHBoxLayout()
        self.btn_find_next = QPushButton("Find Next")
        self.btn_find_next.clicked.connect(self.find_next)
        self.btn_find_prev = QPushButton("Find Previous")
        self.btn_find_prev.clicked.connect(self.find_previous)
        find_btn_layout.addWidget(self.btn_find_next)
        find_btn_layout.addWidget(self.btn_find_prev)
        find_layout.addLayout(find_btn_layout)
        
        layout.addWidget(find_group)
        
        # Replace section
        replace_group = QGroupBox("Replace")
        replace_group.setStyleSheet(find_group.styleSheet())
        replace_layout = QVBoxLayout(replace_group)
        
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Enter replacement text...")
        replace_layout.addWidget(self.replace_input)
        
        replace_btn_layout = QHBoxLayout()
        self.btn_replace = QPushButton("Replace")
        self.btn_replace.clicked.connect(self.replace_one)
        self.btn_replace_all = QPushButton("Replace All")
        self.btn_replace_all.clicked.connect(self.replace_all)
        replace_btn_layout.addWidget(self.btn_replace)
        replace_btn_layout.addWidget(self.btn_replace_all)
        replace_layout.addLayout(replace_btn_layout)
        
        layout.addWidget(replace_group)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
    def find_next(self):
        if not self.editor:
            return
        text = self.find_input.text()
        if not text:
            return

        # Start searching after current selection (if any)
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
            self.editor.setTextCursor(cursor)

        # QTextDocument.find moves the cursor itself; no need to reset on success
        if not self.editor.find(text):
            # Wrap around to start and try again
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            if not self.editor.find(text):
                QMessageBox.information(self, "Not Found", f'"{text}" not found')
    
    def find_previous(self):
        if not self.editor:
            return
        text = self.find_input.text()
        if not text:
            return

        flags = QTextDocument.FindFlag.FindBackward

        # Start searching before current selection (if any)
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart())
            self.editor.setTextCursor(cursor)

        if not self.editor.find(text, flags):
            # Wrap around to end and try again
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            if not self.editor.find(text, flags):
                QMessageBox.information(self, "Not Found", f'"{text}" not found')
    
    def replace_one(self):
        if not self.editor:
            return
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())
    
    def replace_all(self):
        if not self.editor:
            return
        find_text = self.find_input.text()
        replace_text = self.replace_input.text()
        if not find_text:
            return
        
        content = self.editor.toPlainText()
        count = content.count(find_text)
        new_content = content.replace(find_text, replace_text)
        self.editor.setPlainText(new_content)
        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s)")


class ModernButton(QPushButton):
    """Custom button with modern styling."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(32)
        self.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d75;
            }
            QPushButton:disabled {
                background-color: #3e3e3e;
                color: #808080;
            }
        """)


class SecondaryButton(QPushButton):
    """Secondary button style."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(32)
        self.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30;
                color: #cccccc;
                border: 1px solid #3e3e3e;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3e3e3e;
                border-color: #4e4e4e;
            }
            QPushButton:pressed {
                background-color: #252526;
            }
        """)


class SQFtoTCLApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.input_path: Optional[str] = None
        self.output_path: Optional[str] = None
        self.rules_path: Optional[str] = None
        self.db_path: Optional[str] = None
        self.find_replace_dialog: Optional[FindReplaceDialog] = None
        self.config_file = self._get_config_path()
        self._config_loaded = False  # Flag to prevent saving during initialization
        self.init_ui()
        self.apply_dark_theme()
        # Load config after UI is fully initialized
        self.load_config()
        self._config_loaded = True  # Now allow saving
    
    def _get_config_path(self) -> Path:
        """Get path to configuration file."""
        # Try to use project directory first, fallback to user home
        try:
            project_dir = Path(__file__).resolve().parent.parent
            config_path = project_dir / "sqf_converter_config.json"
            return config_path
        except Exception:
            # Fallback to user home directory
            from os.path import expanduser
            home = Path(expanduser("~"))
            return home / ".sqf_converter_config.json"
    
    def save_config(self) -> None:
        """Save current configuration to file."""
        if not self._config_loaded:
            # Don't save during initialization
            return
        try:
            config = {
                "db_path": self.db_path,
                "rules_path": self.rules_path,
                "report_mode": self.report_checkbox.isChecked() if hasattr(self, 'report_checkbox') else True
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception:
            # Silently fail if config can't be saved
            pass
    
    def load_config(self) -> None:
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # Load database path if it exists and file is still valid
                if config.get("db_path"):
                    db_path = config["db_path"]
                    if Path(db_path).exists():
                        self.db_path = db_path
                        if hasattr(self, 'status_label'):
                            self.status_label.setText(f"Database auto-loaded: {Path(db_path).name}")
                    else:
                        # File doesn't exist anymore, remove from config
                        config["db_path"] = None
                        with open(self.config_file, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=2)
                
                # Load rules path if it exists
                if config.get("rules_path") and Path(config["rules_path"]).exists():
                    self.rules_path = config["rules_path"]
                
                # Load report mode preference
                if hasattr(self, 'report_checkbox') and "report_mode" in config:
                    self.report_checkbox.setChecked(config["report_mode"])
        except Exception:
            # Silently fail if config can't be loaded
            pass

    def init_ui(self):
        self.setWindowTitle('SQF to TCL Converter - IDE')
        self.setMinimumSize(1000, 600)
        self.resize(1400, 800)
        
        # Enable high DPI scaling
        if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )

        # Set application icon (uses icon.ico located in project root)
        try:
            icon_path = Path(__file__).resolve().parent.parent / "icon.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            # If icon fails to load, continue without breaking the app
            pass

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Top toolbar
        toolbar = self.create_toolbar()
        main_layout.addWidget(toolbar)

        # Split view for input and output
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2d2d30;
                width: 10px;
            }
            QSplitter::handle:hover {
                background-color: #3e3e3e;
            }
        """)

        # Input panel
        input_panel = self.create_editor_panel("SQF Input", "sqf")
        self.input_editor = input_panel.findChild(CodeEditor)
        self.input_editor.cursorPositionChanged.connect(self.update_status_bar)
        splitter.addWidget(input_panel)

        # Output panel
        output_panel = self.create_editor_panel("TCL Output", "tcl")
        self.output_editor = output_panel.findChild(CodeEditor)
        self.output_editor.setReadOnly(True)
        splitter.addWidget(output_panel)
        
        # Setup keyboard shortcuts for zoom
        from PyQt6.QtGui import QShortcut, QKeySequence
        zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+="), self)
        zoom_in_shortcut.activated.connect(self.zoom_in)
        zoom_in_shortcut2 = QShortcut(QKeySequence("Ctrl++"), self)
        zoom_in_shortcut2.activated.connect(self.zoom_in)
        zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        zoom_out_shortcut.activated.connect(self.zoom_out)
        zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        zoom_reset_shortcut.activated.connect(self.zoom_reset)

        splitter.setSizes([900, 900])
        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #808080;
                padding: 4px;
                font-size: 11px;
            }
        """)
        main_layout.addWidget(self.status_label)

    def create_toolbar(self) -> QFrame:
        """Create the top toolbar with buttons - compact and responsive."""
        toolbar = QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        
        # Horizontal layout for buttons
        layout = QHBoxLayout(toolbar)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        # File operations - Load File (selects and loads in one click)
        file_label = QLabel("File:")
        file_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 35px;")
        file_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(file_label)

        self.btn_load_input = ModernButton("Load File")
        self.btn_load_input.setMinimumWidth(85)
        self.btn_load_input.setMaximumWidth(100)
        self.btn_load_input.clicked.connect(self.load_input_file)
        layout.addWidget(self.btn_load_input)

    

        # Editor operations
        editor_label = QLabel("Editor:")
        editor_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 45px;")
        editor_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(editor_label)

        self.btn_find_replace = SecondaryButton("Find & Replace")
        self.btn_find_replace.setMinimumWidth(95)
        self.btn_find_replace.setMaximumWidth(110)
        self.btn_find_replace.clicked.connect(self.show_find_replace)
        layout.addWidget(self.btn_find_replace)

      

        # Conversion operations
        convert_label = QLabel("Convert:")
        convert_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 55px;")
        convert_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(convert_label)

        self.report_checkbox = QCheckBox("Report")
        self.report_checkbox.setChecked(True)
        self.report_checkbox.toggled.connect(self.save_config)
        self.report_checkbox.setStyleSheet("""
            QCheckBox {
                color: #cccccc;
                spacing: 5px;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 2px solid #3e3e3e;
                border-radius: 3px;
                background-color: #1e1e1e;
            }
            QCheckBox::indicator:checked {
                background-color: #0e639c;
                border-color: #0e639c;
            }
            QCheckBox::indicator:hover {
                border-color: #4e4e4e;
            }
        """)
        layout.addWidget(self.report_checkbox)

        self.btn_convert = ModernButton("Convert")
        self.btn_convert.setStyleSheet("""
            QPushButton {
                background-color: #0e7c0e;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0f9f0f;
            }
            QPushButton:pressed {
                background-color: #0a5f0a;
            }
        """)
        self.btn_convert.setMinimumWidth(80)
        self.btn_convert.setMaximumWidth(100)
        self.btn_convert.clicked.connect(self.convert)
        layout.addWidget(self.btn_convert)


        # Configuration group
        config_label = QLabel("Config:")
        config_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 45px;")
        config_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(config_label)

        self.btn_load_rules = SecondaryButton("Rules")
        self.btn_load_rules.setMinimumWidth(75)
        self.btn_load_rules.setMaximumWidth(100)
        self.btn_load_rules.clicked.connect(self.load_rules)
        layout.addWidget(self.btn_load_rules)

        self.btn_load_db = SecondaryButton("DB")
        self.btn_load_db.setMinimumWidth(75)
        self.btn_load_db.setMaximumWidth(100)
        self.btn_load_db.clicked.connect(self.load_database)
        layout.addWidget(self.btn_load_db)


        # Output operations - Save (like Word) and Save As
        output_label = QLabel("Output:")
        output_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 50px;")
        output_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(output_label)

        self.btn_save_output = ModernButton("Save")
        self.btn_save_output.setMinimumWidth(70)
        self.btn_save_output.setMaximumWidth(85)
        self.btn_save_output.clicked.connect(self.save_output_file)
        layout.addWidget(self.btn_save_output)

        self.btn_save_output_as = SecondaryButton("Save As")
        self.btn_save_output_as.setMinimumWidth(70)
        self.btn_save_output_as.setMaximumWidth(85)
        self.btn_save_output_as.clicked.connect(self.save_output_as)
        layout.addWidget(self.btn_save_output_as)

        layout.addStretch()

        # Zoom controls (right side)
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("color: #cccccc; font-weight: 500; min-width: 40px;")
        zoom_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        layout.addWidget(zoom_label)

        self.btn_zoom_out = SecondaryButton("−")
        self.btn_zoom_out.setMinimumWidth(35)
        self.btn_zoom_out.setMaximumWidth(40)
        self.btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = SecondaryButton("100%")
        self.btn_zoom_reset.setMinimumWidth(50)
        self.btn_zoom_reset.setMaximumWidth(60)
        self.btn_zoom_reset.setToolTip("Reset Zoom (Ctrl+0)")
        self.btn_zoom_reset.clicked.connect(self.zoom_reset)
        layout.addWidget(self.btn_zoom_reset)

        self.btn_zoom_in = SecondaryButton("+")
        self.btn_zoom_in.setMinimumWidth(35)
        self.btn_zoom_in.setMaximumWidth(40)
        self.btn_zoom_in.setToolTip("Zoom In (Ctrl++)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        layout.addWidget(self.btn_zoom_in)

        return toolbar

    def create_editor_panel(self, title: str, language: str) -> QFrame:
        """Create an editor panel with title and code editor."""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                color: #cccccc;
                font-size: 13px;
                font-weight: 600;
                padding: 4px 0;
            }
        """)
        layout.addWidget(title_label)

        # Code editor
        editor = CodeEditor(language=language)
        editor.setPlaceholderText(
            "Paste or load SQF code here..." if language == "sqf" 
            else "Converted TCL output will appear here..."
        )
        layout.addWidget(editor)

        return panel

    def apply_dark_theme(self):
        """Apply dark theme to the application."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
        palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
        palette.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
        palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Link, QColor(14, 99, 156))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(14, 99, 156))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

    def update_status_bar(self):
        """Update status bar with cursor position."""
        line, col = self.input_editor.get_cursor_position()
        self.status_label.setText(f"Line {line}, Column {col}")

    def show_find_replace(self):
        """Show find/replace dialog for input editor."""
        if not self.find_replace_dialog:
            self.find_replace_dialog = FindReplaceDialog(self, self.input_editor)
        self.find_replace_dialog.show()
        self.find_replace_dialog.raise_()
        self.find_replace_dialog.activateWindow()

    def load_input_file(self) -> None:
        """Load input file - selects and loads in one click."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Select and Load SQF file',
            '',
            'SQF files (*.sqf);;All files (*.*)'
        )
        if not path:
            return
        
        try:
            text = Path(path).read_text(encoding='utf-8')
            self.input_editor.setPlainText(text)
            self.input_path = path
            self.status_label.setText(f"Loaded: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Error',
                f'Failed to read input file:\n{e}'
            )

    def convert(self) -> None:
        src = self.input_editor.toPlainText()
        if not src.strip():
            QMessageBox.information(
                self,
                'Empty Input',
                'No SQF input found. Paste or load a file.'
            )
            return
        try:
            report_mode = self.report_checkbox.isChecked()
            out = convert_sqf_string_to_tcl(
                src,
                report=report_mode,
                rules_path=self.rules_path,
                db_path=self.db_path
            )
            self.output_editor.setPlainText(out)
            self.status_label.setText("Conversion completed successfully")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Conversion Error',
                f'Error during conversion:\n{e}'
            )

    def load_rules(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Select rules.yaml',
            '',
            'YAML files (*.yaml *.yml);;All files (*.*)'
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding='utf-8')
            self.input_editor.setPlainText(text)
            self.rules_path = path
            self.save_config()  # Save to cache
            self.status_label.setText(f"Loaded rules: {Path(path).name} (cached)")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Error',
                f'Failed to read rules file:\n{e}'
            )

    def save_rules(self) -> None:
        if not self.rules_path:
            path, _ = QFileDialog.getSaveFileName(
                self,
                'Save rules.yaml',
                '',
                'YAML files (*.yaml *.yml);;All files (*.*)'
            )
            if not path:
                return
            self.rules_path = path
        try:
            text = self.input_editor.toPlainText()
            Path(self.rules_path).write_text(text, encoding='utf-8')
            self.save_config()  # Update cache
            self.status_label.setText(f"Saved rules: {Path(self.rules_path).name}")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Save Error',
                f'Failed to save rules file:\n{e}'
            )

    def load_database(self) -> None:
        """Load argument database from .txt file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Select argument database file',
            '',
            'Text files (*.txt);;All files (*.*)'
        )
        if not path:
            return
        try:
            # Verify file format by reading first few lines
            with open(path, 'r', encoding='utf-8') as f:
                lines = [f.readline().strip() for _ in range(3)]
                # Check if format looks correct (command priority argument)
                valid = any(len(line.split()) >= 3 for line in lines if line)
                if not valid and any(lines):
                    QMessageBox.warning(
                        self,
                        'Format Warning',
                        'File may not be in the expected format.\n'
                        'Expected: <command> <priority> <argument>\n'
                        'Example: CM00001 3 IRU_Drft_Bias'
                    )
            self.db_path = path
            self.save_config()  # Save to cache
            self.status_label.setText(f"Loaded database: {Path(path).name} (cached)")
            QMessageBox.information(
                self,
                'Database Loaded',
                f'Argument database loaded successfully:\n{Path(path).name}\n\n'
                f'Commands will now use arguments from this database.\n'
                f'Path has been saved and will auto-load on next startup.'
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                'Error',
                f'Failed to load database file:\n{e}'
            )

    def save_output_file(self) -> None:
        """Save output - like Word Save: if no path, show dialog; if path exists, save directly."""
        text = self.output_editor.toPlainText()
        if not text.strip():
            QMessageBox.information(
                self,
                'Empty Output',
                'No output to save. Please convert first.'
            )
            return

        # If no path is set, show save dialog (like Save As)
        if not self.output_path:
            path, _ = QFileDialog.getSaveFileName(
                self,
                'Save TCL file',
                '',
                'TCL files (*.tcl);;All files (*.*)'
            )
            if not path:
                return
            self.output_path = path

        # Save to the existing or newly selected path
        try:
            save_tcl_output(text, self.output_path)
            self.status_label.setText(f"Saved: {Path(self.output_path).name}")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Save Error',
                f'Failed to save output:\n{e}'
            )

    def save_output_as(self) -> None:
        """Save output to a different location (like Word Save As)."""
        text = self.output_editor.toPlainText()
        if not text.strip():
            QMessageBox.information(
                self,
                'Empty Output',
                'No output to save. Please convert first.'
            )
            return

        # Always show dialog for Save As
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Save TCL file As',
            self.output_path if self.output_path else '',
            'TCL files (*.tcl);;All files (*.*)'
        )
        if not path:
            return

        try:
            self.output_path = path
            save_tcl_output(text, self.output_path)
            self.status_label.setText(f"Saved as: {Path(self.output_path).name}")
        except Exception as e:
            QMessageBox.critical(
                self,
                'Save Error',
                f'Failed to save output:\n{e}'
            )
    
    def zoom_in(self) -> None:
        """Zoom in both editors."""
        zoom1 = self.input_editor.zoom_in()
        zoom2 = self.output_editor.zoom_in()
        # Update zoom reset button to show current zoom
        zoom_pct = self.input_editor.get_zoom_percentage()
        self.btn_zoom_reset.setText(f"{zoom_pct}%")
    
    def zoom_out(self) -> None:
        """Zoom out both editors."""
        zoom1 = self.input_editor.zoom_out()
        zoom2 = self.output_editor.zoom_out()
        # Update zoom reset button to show current zoom
        zoom_pct = self.input_editor.get_zoom_percentage()
        self.btn_zoom_reset.setText(f"{zoom_pct}%")
    
    def zoom_reset(self) -> None:
        """Reset zoom to 100% for both editors."""
        self.input_editor.zoom_reset()
        self.output_editor.zoom_reset()
        self.btn_zoom_reset.setText("100%")


def run_gui() -> None:
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = SQFtoTCLApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
