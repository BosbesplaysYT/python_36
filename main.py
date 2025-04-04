import sys
import os
import ctypes
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QAction, QFileDialog,
    QMessageBox, QShortcut, QTreeView, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QSplitter, QStackedWidget, QTabWidget, QLabel, QToolButton,
    QScrollArea, QListWidget, QListWidgetItem, QToolTip
)
from PyQt5.QtCore import QFile, QSettings, Qt, QPoint, QTimer, QRegularExpression, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap, QSyntaxHighlighter, QTextCharFormat, QColor, QFont

# --- Low Level Windows API call for dark title bar ---
def set_dark_mode(win_id):
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(win_id), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except Exception as e:
        print("Could not set dark mode:", e)

# --- Syntax Checker Worker (runs in a separate thread) ---
class SyntaxChecker(QObject):
    # Emit a list of error dictionaries: each error has line, col, message.
    syntaxChecked = pyqtSignal(list)
    
    def __init__(self, text):
        super().__init__()
        self.text = text
        
    def run(self):
        errors = []
        try:
            compile(self.text, "<document>", "exec")
        except SyntaxError as e:
            if e.lineno is not None:
                error = {
                    'line': e.lineno - 1,  # 0-based block number.
                    'col': (e.offset - 1) if e.offset is not None else 0,
                    'message': str(e)
                }
                errors.append(error)
        self.syntaxChecked.emit(errors)

# --- Custom Editor Widget with Tooltip Support ---
class CodeEditorWidget(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        super(CodeEditorWidget, self).__init__(*args, **kwargs)
        # Use a fixed-width font.
        self.setFont(QFont("Consolas", 11))
        # Install an event filter on the viewport for hover events.
        self.viewport().installEventFilter(self)
    
    def eventFilter(self, obj, event):
        if obj == self.viewport() and event.type() == event.MouseMove:
            # Get cursor position in document.
            cursor = self.cursorForPosition(event.pos())
            block = cursor.block()
            blockNum = block.blockNumber()
            # If our highlighter (attached as self.highlighter) has error details, check them.
            if hasattr(self, 'highlighter') and hasattr(self.highlighter, 'error_details'):
                if blockNum in self.highlighter.error_details:
                    error_msg = self.highlighter.error_details[blockNum]
                    QToolTip.showText(event.globalPos(), error_msg)
                else:
                    QToolTip.hideText()
        return super(CodeEditorWidget, self).eventFilter(obj, event)

# --- Improved Python Highlighter with Offloaded Syntax Checking and Error Reporting ---
class PythonHighlighter(QSyntaxHighlighter):
    # Signal to update the error panel; emits a list of error dicts.
    errorsUpdated = pyqtSignal(list)
    
    def __init__(self, document):
        super(PythonHighlighter, self).__init__(document)
        self.highlightingRules = []
        self._syntaxTimer = QTimer()
        self._syntaxTimer.setSingleShot(True)
        self._syntaxTimer.timeout.connect(self.checkSyntax)
        # Store errors both as positions and as full error details.
        self.error_positions = {}  # Map block number -> (col, length)
        self.error_details = {}    # Map block number -> error message

        # --- Keyword Formatting ---
        keywordFormat = QTextCharFormat()
        keywordFormat.setForeground(QColor("#569CD6"))
        keywordFormat.setFontWeight(QFont.Bold)
        keywords = [
            "def", "class", "if", "else", "elif", "while", "for", "return",
            "import", "from", "as", "pass", "break", "continue", "try", "except",
            "finally", "with", "lambda", "None", "True", "False", "in", "not", "and", "or"
        ]
        for word in keywords:
            pattern = QRegularExpression(r'\b' + word + r'\b')
            self.highlightingRules.append((pattern, keywordFormat))

        # --- Comment Formatting ---
        commentFormat = QTextCharFormat()
        commentFormat.setForeground(QColor("#6A9955"))
        commentPattern = QRegularExpression(r'#.*')
        self.highlightingRules.append((commentPattern, commentFormat))

        # --- String Literal Formatting ---
        stringFormat = QTextCharFormat()
        stringFormat.setForeground(QColor("#D69D85"))
        stringPattern = QRegularExpression(r'(\".*?\"|\'.*?\')')
        self.highlightingRules.append((stringPattern, stringFormat))

        # --- Number Formatting ---
        numberFormat = QTextCharFormat()
        numberFormat.setForeground(QColor("#B5CEA8"))
        numberPattern = QRegularExpression(r'\b[0-9]+(\.[0-9]+)?\b')
        self.highlightingRules.append((numberPattern, numberFormat))

        # --- Function Definition Formatting (heuristic) ---
        funcFormat = QTextCharFormat()
        funcFormat.setForeground(QColor("#DCDCAA"))
        funcPattern = QRegularExpression(r'\bdef\s+([A-Za-z_][A-Za-z0-9_]*)')
        self.highlightingRules.append((funcPattern, funcFormat))

        # --- Triple-quoted String Formatting ---
        self.tripleQuoteFormat = QTextCharFormat()
        self.tripleQuoteFormat.setForeground(QColor("#D69D85"))

        # --- Syntax Error Formatting ---
        self.errorFormat = QTextCharFormat()
        self.errorFormat.setUnderlineColor(QColor("red"))
        self.errorFormat.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

        # Trigger syntax check when document changes.
        document.contentsChanged.connect(self.triggerSyntaxCheck)

    def triggerSyntaxCheck(self):
        self._syntaxTimer.start(300)

    def checkSyntax(self):
        text = self.document().toPlainText()
        self.syntaxThread = QThread()
        self.syntaxWorker = SyntaxChecker(text)
        self.syntaxWorker.moveToThread(self.syntaxThread)
        self.syntaxThread.started.connect(self.syntaxWorker.run)
        self.syntaxWorker.syntaxChecked.connect(self.onSyntaxChecked)
        self.syntaxWorker.syntaxChecked.connect(self.syntaxThread.quit)
        self.syntaxWorker.syntaxChecked.connect(self.syntaxWorker.deleteLater)
        self.syntaxThread.finished.connect(self.syntaxThread.deleteLater)
        self.syntaxThread.start()

    def onSyntaxChecked(self, errors):
        # Reset error dictionaries.
        self.error_positions = {}
        self.error_details = {}
        for error in errors:
            self.error_positions[error['line']] = (error['col'], 1)
            self.error_details[error['line']] = error['message']
        self.errorsUpdated.emit(errors)
        self.rehighlight()

    def highlightBlock(self, text):
        # Apply syntax rules.
        for pattern, fmt in self.highlightingRules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart()
                length = match.capturedLength()
                self.setFormat(start, length, fmt)
        # Handle triple-quoted strings.
        for delimiter in ['"""', "'''"]:
            self.highlightMultiline(text, delimiter)
        # Underline errors.
        block_num = self.currentBlock().blockNumber()
        if block_num in self.error_positions:
            col, length = self.error_positions[block_num]
            if col < len(text):
                self.setFormat(col, length, self.errorFormat)

    def highlightMultiline(self, text, delimiter):
        startIndex = 0
        if self.previousBlockState() != 1:
            startIndex = text.find(delimiter)
        else:
            startIndex = 0
        while startIndex >= 0:
            endIndex = text.find(delimiter, startIndex + len(delimiter))
            if endIndex == -1:
                self.setCurrentBlockState(1)
                stringLength = len(text) - startIndex
            else:
                stringLength = endIndex - startIndex + len(delimiter)
            self.setFormat(startIndex, stringLength, self.tripleQuoteFormat)
            startIndex = text.find(delimiter, startIndex + stringLength)
        if self.currentBlockState() != 1:
            self.setCurrentBlockState(0)

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
        self.btnClose = QToolButton(self)
        self.btnClose.setText("✖")
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
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.openFiles = {}  # Map file paths to their editor widgets.
        self.settings = QSettings("MyCompany", "PyQtCodeEditor")
        self.initUI()
        self.restoreAppState()

    def initUI(self):
        self.titleBar = CustomTitleBar(self)
        self.tabWidget = QTabWidget()
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self.closeTab)
        self.tabWidget.currentChanged.connect(self.onTabChanged)
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
        self.sideBar = self.createSideBar()
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.sideBar)
        self.splitter.addWidget(self.tabWidget)
        self.splitter.setStretchFactor(1, 1)
        # Bottom error panel.
        self.errorList = QListWidget()
        self.errorList.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
        self.errorList.itemClicked.connect(self.onErrorItemClicked)
        # Layout: title bar, splitter, then error list.
        centralWidget = QWidget()
        centralLayout = QVBoxLayout(centralWidget)
        centralLayout.setContentsMargins(0, 0, 0, 0)
        centralLayout.setSpacing(0)
        centralLayout.addWidget(self.titleBar)
        centralLayout.addWidget(self.splitter)
        centralLayout.addWidget(self.errorList)
        self.setCentralWidget(centralWidget)
        self.createMenuBar()
        self.setGeometry(100, 100, 1200, 700)
        self.applyDarkTheme()
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save.activated.connect(self.handleSave)
        set_dark_mode(self.winId())

    def createMenuBar(self):
        menubar = self.menuBar()
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
        sidebarWidget = QWidget()
        layout = QHBoxLayout(sidebarWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        iconBar = QWidget()
        iconBarLayout = QVBoxLayout(iconBar)
        iconBarLayout.setContentsMargins(0, 0, 0, 0)
        iconBar.setFixedWidth(40)
        fsButton = QPushButton("FS")
        fsButton.setFixedWidth(40)
        fsButton.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
        iconBarLayout.addWidget(fsButton)
        iconBarLayout.addStretch()
        contentWidget = QWidget()
        contentLayout = QVBoxLayout(contentWidget)
        contentLayout.setContentsMargins(5, 5, 5, 5)
        self.dirLabel = QLabel("No directory opened")
        self.dirLabel.setStyleSheet("color: #ffffff; font-size: 10pt;")
        contentLayout.addWidget(self.dirLabel)
        self.fsTreeView = QTreeView()
        from PyQt5.QtWidgets import QFileSystemModel
        self.fsModel = QFileSystemModel()
        self.fsModel.setRootPath("")
        self.fsTreeView.setModel(self.fsModel)
        for i in range(1, self.fsModel.columnCount()):
            self.fsTreeView.hideColumn(i)
        self.fsTreeView.doubleClicked.connect(self.onTreeDoubleClicked)
        self.fsTreeView.setStyleSheet("background-color: #313335; color: #ffffff;")
        contentLayout.addWidget(self.fsTreeView)
        self.sidebarStack = QStackedWidget()
        self.sidebarStack.addWidget(contentWidget)
        layout.addWidget(iconBar)
        layout.addWidget(self.sidebarStack)
        sidebarWidget.setFixedWidth(300)
        return sidebarWidget

    def onTreeDoubleClicked(self, index):
        file_path = self.fsModel.filePath(index)
        if os.path.isfile(file_path):
            self.openFileInTab(file_path)

    def openFileInTab(self, file_path):
        if file_path in self.openFiles:
            index = self.tabWidget.indexOf(self.openFiles[file_path])
            self.tabWidget.setCurrentIndex(index)
            return
        filename = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        image_exts = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        if ext in image_exts:
            label = QLabel()
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                QMessageBox.warning(self, "Error", f"Could not open image: {file_path}")
                return
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            scrollArea = QScrollArea()
            scrollArea.setWidget(label)
            scrollArea.setWidgetResizable(True)
            self.tabWidget.addTab(scrollArea, filename)
            self.tabWidget.setCurrentWidget(scrollArea)
            self.openFiles[file_path] = scrollArea
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            is_text = True
        except UnicodeDecodeError:
            is_text = False
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file: {file_path}\n{e}")
            return
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
                try:
                    with open(file_path, 'rb') as f:
                        raw = f.read()
                    text = raw.decode('utf-8', errors='replace')
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not open file: {file_path}\n{e}")
                    return
        editor = CodeEditorWidget()
        editor.setPlainText(text)
        editor.setStyleSheet("background-color: #313335; color: #ffffff;")
        if file_path.endswith(".py"):
            editor.highlighter = PythonHighlighter(editor.document())
            # Connect highlighter signal to update error list.
            editor.highlighter.errorsUpdated.connect(self.updateErrorList)
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
        if currentText != editor.originalText:
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
            self.openFiles[file_path] = editor
            current_index = self.tabWidget.currentIndex()
            self.tabWidget.setTabText(current_index, os.path.basename(file_path))
            self.saveToFile(file_path, editor)

    def closeTab(self, index):
        widget = self.tabWidget.widget(index)
        for path, editor in list(self.openFiles.items()):
            if editor == widget:
                del self.openFiles[path]
                break
        self.tabWidget.removeTab(index)
        # Clear error list if no tabs remain.
        if self.tabWidget.count() == 0:
            self.errorList.clear()

    def openDirectory(self):
        options = QFileDialog.Options()
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", "", options=options)
        if directory:
            self.dirLabel.setText(f"Folder: {directory}")
            index = self.fsModel.setRootPath(directory)
            self.fsTreeView.setRootIndex(index)

    def updateErrorList(self, errors):
        self.errorList.clear()
        for error in errors:
            # Display line number (1-based) and a snippet of the error message.
            item_text = f"Line {error['line']+1}: {error['message']}"
            item = QListWidgetItem(item_text)
            # Store the line number in the item for navigation.
            item.setData(Qt.UserRole, error['line'])
            self.errorList.addItem(item)

    def onErrorItemClicked(self, item):
        line = item.data(Qt.UserRole)
        currentEditor = self.tabWidget.currentWidget()
        if currentEditor:
            # Move cursor to the beginning of the error line.
            cursor = currentEditor.textCursor()
            block = currentEditor.document().findBlockByNumber(line)
            cursor.setPosition(block.position())
            currentEditor.setTextCursor(cursor)
            currentEditor.setFocus()

    def onTabChanged(self, index):
        # Clear error list when switching tabs if highlighter isn't available.
        currentEditor = self.tabWidget.widget(index)
        if currentEditor and hasattr(currentEditor, 'highlighter'):
            # Trigger a syntax check to update error list.
            currentEditor.highlighter.triggerSyntaxCheck()
        else:
            self.errorList.clear()

    def applyDarkTheme(self):
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
        QTabWidget::pane {
            border-top: 2px solid #313335;
        }
        """
        self.setStyleSheet(darkStyleSheet)

    def closeEvent(self, event):
        self.saveAppState()
        event.accept()

    def saveAppState(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("openFiles", list(self.openFiles.keys()))
        self.settings.setValue("activeTab", self.tabWidget.currentIndex())
        self.settings.setValue("openDirectory", self.dirLabel.text())
        
    def restoreAppState(self):
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        files = self.settings.value("openFiles")
        if files:
            for file_path in files:
                if os.path.exists(file_path):
                    self.openFileInTab(file_path)
        activeTab = self.settings.value("activeTab")
        if activeTab is not None and self.tabWidget.count() > int(activeTab):
            self.tabWidget.setCurrentIndex(int(activeTab))
        openDir = self.settings.value("openDirectory")
        if openDir and openDir.startswith("Folder:"):
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
