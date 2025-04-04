import sys
import os
import ctypes
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QAction, QFileDialog,
    QMessageBox, QShortcut, QTreeView, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QStackedWidget, QTabWidget, QLabel, QToolButton
)
from PyQt5.QtCore import QFile, QTextStream, Qt, QPoint, QSettings
from PyQt5.QtGui import QKeySequence, QIcon
from PyQt5.QtWidgets import QFileSystemModel
from PyQt5.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt5.QtCore import QRegularExpression
from PyQt5.QtWidgets import QToolButton, QTabBar
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QScrollArea

# --- Low Level Windows API call for dark title bar ---
def set_dark_mode(win_id):
    # Only works on Windows 10/11
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(win_id), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except Exception as e:
        print("Could not set dark mode:", e)

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super(PythonHighlighter, self).__init__(document)
        self.highlightingRules = []

        # Keyword formatting
        keywordFormat = QTextCharFormat()
        keywordFormat.setForeground(QColor("#569CD6"))
        keywordFormat.setFontWeight(QFont.Bold)
        keywords = [
            "def", "class", "if", "else", "elif", "while", "for", "return", 
            "import", "from", "as", "pass", "break", "continue", "try", "except", 
            "finally", "with", "lambda", "None", "True", "False"
        ]
        for word in keywords:
            pattern = QRegularExpression(r'\b' + word + r'\b')
            self.highlightingRules.append((pattern, keywordFormat))

        # Comment formatting
        commentFormat = QTextCharFormat()
        commentFormat.setForeground(QColor("#6A9955"))
        commentPattern = QRegularExpression(r'#.*')
        self.highlightingRules.append((commentPattern, commentFormat))

        # String literal formatting
        stringFormat = QTextCharFormat()
        stringFormat.setForeground(QColor("#D69D85"))
        # This regex covers both single and double quotes (basic handling).
        stringPattern = QRegularExpression(r'(\".*\"|\'.*\')')
        self.highlightingRules.append((stringPattern, stringFormat))

        # Number formatting
        numberFormat = QTextCharFormat()
        numberFormat.setForeground(QColor("#B5CEA8"))
        numberPattern = QRegularExpression(r'\b[0-9]+(\.[0-9]+)?\b')
        self.highlightingRules.append((numberPattern, numberFormat))

        # Function definition (simple heuristic)
        funcFormat = QTextCharFormat()
        funcFormat.setForeground(QColor("#DCDCAA"))
        funcPattern = QRegularExpression(r'\bdef\s+([A-Za-z_][A-Za-z0-9_]*)')
        self.highlightingRules.append((funcPattern, funcFormat))


    def highlightBlock(self, text):
        for pattern, fmt in self.highlightingRules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                self.setFormat(start, length, fmt)


# --- Custom Title Bar ---
class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.initUI()
        self.startPos = None

    def initUI(self):
        self.setFixedHeight(35)
        self.setStyleSheet("""
            background-color: #2b2b2b;
            color: #ffffff;
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(10)
        
        layout.addStretch()
        
        # Right: System buttons (minimize, maximize, close)
        self.btnMin = QToolButton(self)
        self.btnMin.setText("—")
        self.btnMin.setStyleSheet("background-color: #3c3c3c; color: #ffffff; border: none; padding: 5px;")
        self.btnMin.clicked.connect(self.parent.showMinimized)
        layout.addWidget(self.btnMin)
        
        self.btnMax = QToolButton(self)
        self.btnMax.setText("▢")
        self.btnMax.setStyleSheet("background-color: #3c3c3c; color: #ffffff; border: none; padding: 5px;")
        self.btnMax.clicked.connect(self.toggleMaxRestore)
        layout.addWidget(self.btnMax)
        
        # Replace the close button creation in CustomTitleBar.initUI:
        self.btnClose = QToolButton(self)
        # Use a simple white cross. You can experiment with Unicode characters.
        self.btnClose.setText("✖")
        # Update the style sheet to remove background or use a flat look.
        self.btnClose.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #ffffff;
                border: none;
                font-size: 14pt;
            }
            QToolButton:hover {
                color: #ff5555;
            }
        """)
        self.btnClose.clicked.connect(self.parent.close)
        layout.addWidget(self.btnClose)


    def toggleMaxRestore(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.btnMax.setText("▢")
        else:
            self.parent.showMaximized()
            self.btnMax.setText("❐")

    # Allow dragging of the window by the title bar.
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.startPos = event.globalPos()
            self.clickPos = self.mapToParent(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.startPos:
            delta = event.globalPos() - self.startPos
            self.parent.move(self.parent.pos() + delta)
            self.startPos = event.globalPos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.startPos = None
        super().mouseReleaseEvent(event)

# --- Main Code Editor ---
class CodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        # Remove native title bar to use our custom one
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.openFiles = {}  # Map file paths to their corresponding editor widgets
        self.settings = QSettings("MyCompany", "PyQtCodeEditor")
        self.initUI()
        self.restoreAppState()

    def initUI(self):
        # Create custom title bar and add it to the window layout.
        self.titleBar = CustomTitleBar(self)
        
        # Create the tab widget to hold multiple editors.
        self.tabWidget = QTabWidget()
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self.closeTab)
        self.tabWidget.setStyleSheet("""
            QTabBar::tab {
                background: #3c3c3c;
                color: #ffffff;
                padding: 5px;
            }
            QTabBar::tab:selected {
                background: #313335;
            }
        """)
        
        # Create the sidebar widget (holds the icon bar and dynamic content)
        self.sideBar = self.createSideBar()
        
        # Create a splitter to hold the sidebar and the tab widget
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.sideBar)
        self.splitter.addWidget(self.tabWidget)
        self.splitter.setStretchFactor(1, 1)  # Make tabs take up remaining space

        # Central widget will be a vertical layout: custom title bar on top, then the splitter.
        centralWidget = QWidget()
        centralLayout = QVBoxLayout(centralWidget)
        centralLayout.setContentsMargins(0, 0, 0, 0)
        centralLayout.setSpacing(0)
        centralLayout.addWidget(self.titleBar)
        centralLayout.addWidget(self.splitter)
        self.setCentralWidget(centralWidget)
        
        # Set up the menu bar with file and directory operations.
        # (We add these actions to our QMainWindow even though we have a custom title bar.)
        self.createMenuBar()
        
        # Set window geometry and apply dark theme.
        self.setGeometry(100, 100, 1200, 700)
        self.applyDarkTheme()
        
        # Add keyboard shortcut for saving (Ctrl+S).
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.handleSave)
        
        # Set dark mode for the window decorations using low-level API (Windows only).
        set_dark_mode(self.winId())

    def createMenuBar(self):
        menubar = self.menuBar()
        # Even though our native title bar is replaced, QMenuBar still appears below it.
        fileMenu = menubar.addMenu('File')

        openAction = QAction('Open File', self)
        openAction.triggered.connect(self.openFile)
        fileMenu.addAction(openAction)

        saveAction = QAction('Save', self)
        saveAction.triggered.connect(self.handleSave)
        fileMenu.addAction(saveAction)
        
        openDirAction = QAction('Open Directory', self)
        openDirAction.triggered.connect(self.openDirectory)
        fileMenu.addAction(openDirAction)

        exitAction = QAction('Exit', self)
        exitAction.triggered.connect(self.close)
        fileMenu.addAction(exitAction)

    def createSideBar(self):
        """
        Creates a widget that holds two sidebars:
        - A narrow icon bar on the left.
        - A dynamic content area on the right (currently set to display a filesystem tree view with a header label).
        """
        sidebarWidget = QWidget()
        layout = QHBoxLayout(sidebarWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Left Icon Bar (narrow)
        iconBar = QWidget()
        iconBarLayout = QVBoxLayout(iconBar)
        iconBarLayout.setContentsMargins(0, 0, 0, 0)
        iconBar.setFixedWidth(40)
        
        # For now, add a single button representing the file system.
        fsButton = QPushButton("FS")
        fsButton.setFixedWidth(40)
        fsButton.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
        iconBarLayout.addWidget(fsButton)
        iconBarLayout.addStretch()

        # Right Sidebar Content Area using a vertical layout.
        contentWidget = QWidget()
        contentLayout = QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(5, 5, 5, 5)
        
        # Label to show current directory.
        self.dirLabel = QLabel("No directory opened")
        self.dirLabel.setStyleSheet("color: #ffffff; font-size: 10pt;")
        contentLayout.addWidget(self.dirLabel)
        
        # File system tree view.
        self.fsTreeView = QTreeView()
        self.fsModel = QFileSystemModel()
        self.fsModel.setRootPath("")  # Start with an empty root.
        self.fsTreeView.setModel(self.fsModel)
        # Hide unnecessary columns; show only file/folder names.
        for i in range(1, self.fsModel.columnCount()):
            self.fsTreeView.hideColumn(i)
        # Connect double-click signal to open files.
        self.fsTreeView.doubleClicked.connect(self.onTreeDoubleClicked)
        # Style for dark theme.
        self.fsTreeView.setStyleSheet("background-color: #313335; color: #ffffff;")
        contentLayout.addWidget(self.fsTreeView)
        
        # Use QStackedWidget if you plan to add more dynamic sidebar content.
        self.sidebarStack = QStackedWidget()
        self.sidebarStack.addWidget(contentWidget)
        
        layout.addWidget(iconBar)
        layout.addWidget(self.sidebarStack)
        sidebarWidget.setFixedWidth(300)  # Overall sidebar width.
        return sidebarWidget

    def onTreeDoubleClicked(self, index):
        # Get full path of the clicked item.
        file_path = self.fsModel.filePath(index)
        # If it's a file, open it in a new tab.
        if os.path.isfile(file_path):
            self.openFileInTab(file_path)


    def openFileInTab(self, file_path):
        # If the file is already open, switch to its tab.
        if file_path in self.openFiles:
            index = self.tabWidget.indexOf(self.openFiles[file_path])
            self.tabWidget.setCurrentIndex(index)
            return

        filename = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']

        # --- Handle image files ---
        if ext in image_exts:
            label = QLabel()
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                QMessageBox.warning(self, "Error", f"Could not open image: {file_path}")
                return
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)

            # Optional: Use a scroll area if the image is large
            scrollArea = QScrollArea()
            scrollArea.setWidget(label)
            scrollArea.setWidgetResizable(True)

            self.tabWidget.addTab(scrollArea, filename)
            self.tabWidget.setCurrentWidget(scrollArea)
            self.openFiles[file_path] = scrollArea
            return

        # --- Attempt to open file as text ---
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            is_text = True
        except UnicodeDecodeError:
            is_text = False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file: {file_path}\n{e}")
            return

        # --- If file isn't text-based (and isn't an image) ---
        if not is_text:
            reply = QMessageBox.question(
                self, 
                "Binary file",
                f"The file {filename} does not appear to be text-based. Open it anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            else:
                # Open the file in binary mode and decode with errors replaced.
                try:
                    with open(file_path, 'rb') as f:
                        raw = f.read()
                    text = raw.decode('utf-8', errors='replace')
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not open file: {file_path}\n{e}")
                    return

        # --- Create a text editor for text-based files ---
        editor = QTextEdit()
        editor.setPlainText(text)
        editor.setStyleSheet("background-color: #313335; color: #ffffff;")
        
        # Add syntax highlighting for Python files.
        if file_path.endswith(".py"):
            editor.highlighter = PythonHighlighter(editor.document())

        # Save the original text for unsaved changes tracking.
        editor.originalText = text
        editor.textChanged.connect(lambda: self.updateTabTitle(editor, file_path))

        index = self.tabWidget.addTab(editor, filename)
        self.tabWidget.setCurrentWidget(editor)
        self.openFiles[file_path] = editor




    def openFile(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Files (*);;Python Files (*.py)",
            options=options
        )
        if file_path:
            self.openFileInTab(file_path)

    def updateTabTitle(self, editor, file_path):
        index = self.tabWidget.indexOf(editor)
        filename = os.path.basename(file_path)
        currentText = editor.toPlainText()
        # If the text differs from the original, mark as unsaved.
        if currentText != editor.originalText:
            # Add a white dot (●) to indicate unsaved changes.
            title = f"{filename} ●"
        else:
            title = filename
        self.tabWidget.setTabText(index, title)

    def handleSave(self):
        currentEditor = self.tabWidget.currentWidget()
        if not currentEditor:
            return
        file_path = None
        for path, editor in self.openFiles.items():
            if editor == currentEditor:
                file_path = path
                break
        if file_path:
            self.saveToFile(file_path, currentEditor)
            # After saving, update the original text and remove the unsaved marker.
            currentEditor.originalText = currentEditor.toPlainText()
            self.updateTabTitle(currentEditor, file_path)
        else:
            self.saveFileAs(currentEditor)

    def saveToFile(self, file_path, editor):
        file = QFile(file_path)
        if file.open(QFile.WriteOnly | QFile.Text):
            text = editor.toPlainText()
            file.write(text.encode())
            file.close()
        else:
            QMessageBox.warning(self, "Error", "Could not save file!")

    def saveFileAs(self, editor):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            "",
            "All Files (*);;Python Files (*.py)",
            options=options
        )
        if file_path:
            # Update mapping.
            self.openFiles[file_path] = editor
            # Change the tab title.
            current_index = self.tabWidget.currentIndex()
            self.tabWidget.setTabText(current_index, os.path.basename(file_path))
            self.saveToFile(file_path, editor)

    def closeTab(self, index):
        widget = self.tabWidget.widget(index)
        # Remove widget from the mapping.
        for path, editor in list(self.openFiles.items()):
            if editor == widget:
                del self.openFiles[path]
                break
        self.tabWidget.removeTab(index)

    def openDirectory(self):
        """
        Opens a directory dialog, updates the file system tree view,
        and sets the label to the selected directory.
        """
        options = QFileDialog.Options()
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", "", options=options)
        if directory:
            # Update the label.
            self.dirLabel.setText(f"Folder: {directory}")
            # Set the file system model's root.
            index = self.fsModel.setRootPath(directory)
            self.fsTreeView.setRootIndex(index)

    def applyDarkTheme(self):
        # Overall dark stylesheet.
        darkStyleSheet = """
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-size: 12pt;
        }
        QMenuBar {
            background-color: #2b2b2b;
        }
        QMenuBar::item {
            background-color: #2b2b2b;
        }
        QMenuBar::item:selected {
            background-color: #3c3c3c;
        }
        QMenu {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QMenu::item:selected {
            background-color: #3c3c3c;
        }
        QTabWidget::pane { /* The tab widget frame */
            border-top: 2px solid #313335;
        }
        """
        self.setStyleSheet(darkStyleSheet)

    def closeEvent(self, event):
        """Save state when closing."""
        self.saveAppState()
        event.accept()

    def saveAppState(self):
        # Save window geometry and state.
        self.settings.setValue("geometry", self.saveGeometry())
        # Save open files (only file paths; unsaved changes are not handled here).
        self.settings.setValue("openFiles", list(self.openFiles.keys()))
        # Save active tab index.
        self.settings.setValue("activeTab", self.tabWidget.currentIndex())
        # Save open directory (from the label).
        self.settings.setValue("openDirectory", self.dirLabel.text())
        
    def restoreAppState(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        # Restore open files.
        files = self.settings.value("openFiles")
        if files:
            # If multiple files were open, open them in tabs.
            for file_path in files:
                if os.path.exists(file_path):
                    self.openFileInTab(file_path)
        # Restore active tab index.
        activeTab = self.settings.value("activeTab")
        if activeTab is not None and self.tabWidget.count() > int(activeTab):
            self.tabWidget.setCurrentIndex(int(activeTab))
        # Restore open directory label.
        openDir = self.settings.value("openDirectory")
        if openDir and openDir.startswith("Folder:"):
            # Extract the path from the label text.
            directory = openDir.split("Folder:")[1].strip()
            if os.path.isdir(directory):
                self.dirLabel.setText(openDir)
                index = self.fsModel.setRootPath(directory)
                self.fsTreeView.setRootIndex(index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = CodeEditor()
    editor.show()
    sys.exit(app.exec_())
