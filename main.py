import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QAction, QFileDialog, QMessageBox
from PyQt5.QtCore import QFile, QTextStream

class CodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # Create a text editor widget
        self.textEdit = QTextEdit()
        self.setCentralWidget(self.textEdit)
        
        # Set up the menu bar with basic file operations
        self.createMenuBar()
        
        # Set window title and dimensions
        self.setWindowTitle("PyQt Code Editor")
        self.setGeometry(100, 100, 800, 600)
        
        # Apply the dark theme immediately
        self.applyDarkTheme()

    def createMenuBar(self):
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('File')

        openAction = QAction('Open', self)
        openAction.triggered.connect(self.openFile)
        fileMenu.addAction(openAction)

        saveAction = QAction('Save', self)
        saveAction.triggered.connect(self.saveFile)
        fileMenu.addAction(saveAction)

        exitAction = QAction('Exit', self)
        exitAction.triggered.connect(self.close)
        fileMenu.addAction(exitAction)

    def openFile(self):
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Files (*);;Python Files (*.py)",
            options=options
        )
        if fileName:
            file = QFile(fileName)
            if file.open(QFile.ReadOnly | QFile.Text):
                textStream = QTextStream(file)
                text = textStream.readAll()
                self.textEdit.setPlainText(text)
                file.close()
            else:
                QMessageBox.warning(self, "Error", "Could not open file!")

    def saveFile(self):
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            "",
            "All Files (*);;Python Files (*.py)",
            options=options
        )
        if fileName:
            file = QFile(fileName)
            if file.open(QFile.WriteOnly | QFile.Text):
                text = self.textEdit.toPlainText()
                file.write(text.encode())
                file.close()
            else:
                QMessageBox.warning(self, "Error", "Could not save file!")

    def applyDarkTheme(self):
        # This stylesheet sets a dark theme for the main window and widgets.
        darkStyleSheet = """
        /* General Widget Styles */
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-size: 12pt;
        }
        /* Menu Bar Styles */
        QMenuBar {
            background-color: #2b2b2b;
        }
        QMenuBar::item {
            background-color: #2b2b2b;
        }
        QMenuBar::item:selected {
            background-color: #3c3c3c;
        }
        /* Menu Styles */
        QMenu {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QMenu::item:selected {
            background-color: #3c3c3c;
        }
        /* Text Edit Styles */
        QTextEdit {
            background-color: #313335;
            color: #ffffff;
        }
        """
        self.setStyleSheet(darkStyleSheet)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = CodeEditor()
    editor.show()
    sys.exit(app.exec_())
