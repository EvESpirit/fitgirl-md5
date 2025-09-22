#!/usr/bin/env python3
import hashlib
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# PyQt6 Imports
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QLabel, QFileDialog, QStatusBar, QHeaderView, QStackedWidget
)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QColor, QFont, QBrush

MANIFEST_FILENAME = "fitgirl-bins.md5"
MD5_SUBFOLDER = "MD5"

# Dark Theme Stylesheet
DARK_STYLESHEET = """
QWidget {
    background-color: #2b2b2b;
    color: #f0f0f0;
    font-family: Segoe UI, sans-serif;
    font-size: 10pt;
}
QMainWindow {
    border: 1px solid #1e1e1e;
}
QTableWidget {
    gridline-color: #444;
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 4px;
}
QTableWidget::item {
    padding-left: 5px;
    border-bottom: 1px solid #444;
}
QHeaderView::section {
    background-color: #444;
    padding: 4px;
    border: 1px solid #555;
    font-weight: bold;
}
QPushButton {
    background-color: #007acc;
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #008ae6;
}
QPushButton:pressed {
    background-color: #006bb3;
}
QPushButton:disabled {
    background-color: #404040;
    color: #888;
}
QPushButton#quitButton {
    background-color: #c62828;
}
QPushButton#quitButton:hover {
    background-color: #e53935;
}
QPushButton#quitButton:pressed {
    background-color: #b71c1c;
}
QLineEdit {
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    color: #f0f0f0;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #007acc;
    border-radius: 3px;
    margin: 1px;
}
QStatusBar {
    font-size: 9pt;
}
QLabel#titleLabel {
    font-size: 14pt;
    font-weight: bold;
    padding-bottom: 5px;
}
"""


# Core Verification Logic
def calculateMd5(filepath, blockSize=655360, progressCallback=None, isRunningCheck=None):
    """
    Calculates the MD5 hash of a file with progress reporting and cancellation support.
    """
    md5 = hashlib.md5()
    try:
        totalSize = os.path.getsize(filepath)
        bytesRead = 0
        lastPercentage = -1
        with open(filepath, 'rb') as f:
            while True:
                if isRunningCheck and not isRunningCheck():
                    return "CANCELLED"
                data = f.read(blockSize)
                if not data:
                    break
                md5.update(data)
                bytesRead += len(data)
                if progressCallback and totalSize > 0:
                    # Only emit the signal if the percentage value has changed.
                    currentPercentage = int((bytesRead / totalSize) * 100)
                    if currentPercentage > lastPercentage:
                        progressCallback(currentPercentage)
                        lastPercentage = currentPercentage

        # Ensure the progress bar always hits 100% on completion.
        if progressCallback and lastPercentage < 100:
            progressCallback(100)

        return md5.hexdigest()
    except FileNotFoundError:
        return None
    except IOError:
        return "IO_ERROR"


class VerificationController(QObject):
    """
    Manages the multithreaded file verification process.
    """
    fileProgress = pyqtSignal(int, int)
    fileFinished = pyqtSignal(int, str, QColor)
    allFinished = pyqtSignal(dict)

    def __init__(self, tasks):
        super().__init__()
        self.tasks = tasks
        self.isRunning = True
        self.threadCount = os.cpu_count() or 1
        self.executor = None

    def run(self):
        """
        Runs verification tasks in a thread pool.
        """
        summary = {"ok": 0, "failed": 0, "missing": 0, "error": 0, "total": len(self.tasks), "time": 0.0}
        startTime = time.perf_counter()

        self.executor = ThreadPoolExecutor(max_workers=self.threadCount)
        futures = {self.executor.submit(self.processFile, i, task): i for i, task in enumerate(self.tasks)}

        try:
            for future in as_completed(futures):
                if not self.isRunning:
                    break
                try:
                    statusCode = future.result()
                    if statusCode:
                        summary[statusCode.lower()] += 1
                except Exception:
                    # Exceptions may occur if a future is cancelled.
                    pass
        finally:
            if self.isRunning:
                self.executor.shutdown(wait=True)

        endTime = time.perf_counter()
        summary["time"] = endTime - startTime
        if self.isRunning:
            self.allFinished.emit(summary)

    def processFile(self, index, taskDetails):
        """
        Processes a single file, checks existence and calculates its hash.
        """
        if not self.isRunning:
            return "CANCELLED"

        filepath, expectedHash, _ = taskDetails
        if not os.path.exists(filepath):
            self.fileFinished.emit(index, "MISSING", QColor("#ff5555"))
            return "MISSING"

        progressCallback = lambda p: self.fileProgress.emit(index, p) if self.isRunning else None
        isRunningCheck = lambda: self.isRunning
        actualMd5 = calculateMd5(filepath, progressCallback=progressCallback, isRunningCheck=isRunningCheck)

        if not self.isRunning or actualMd5 == "CANCELLED":
            return "CANCELLED"
        if actualMd5 is None:
            self.fileFinished.emit(index, "MISSING", QColor("#ff5555"))
            return "MISSING"
        if actualMd5 == "IO_ERROR":
            self.fileFinished.emit(index, "I/O ERROR", QColor("#ff9900"))
            return "ERROR"

        if actualMd5.lower() == expectedHash.lower():
            self.fileFinished.emit(index, "OK", QColor("#55ff55"))
            return "OK"
        else:
            self.fileFinished.emit(index, "FAILED", QColor("#ff5555"))
            return "FAILED"

    def stop(self):
        """
        Non-blocking shutdown of the thread pool.
        """
        self.isRunning = False
        if self.executor:
            # Tell the executor to shut down without waiting for tasks to finish.
            if sys.version_info >= (3, 9):
                self.executor.shutdown(wait=False, cancel_futures=True)
            else:
                self.executor.shutdown(wait=False)


# GUI
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FitGirl Repack Verifier")
        self.initialSize = (1200, 600)
        self.setGeometry(100, 100, self.initialSize[0], self.initialSize[1])
        self.setMinimumSize(700, 400)
        self.setWindowIcon(QIcon(self.createAppIcon()))

        self.workerThread = None
        self.controller = None
        self.tasks = []

        self.initializeUi()

    def createAppIcon(self):
        """I was bored bored. Fuck you! *unfiles your icon*"""
        from PyQt6.QtGui import QPixmap, QPainter
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#007acc"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 60, 60)
        p.setBrush(QColor("#ffffff"))
        p.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "✓")
        p.end()
        return pixmap

    def initializeUi(self):
        """Sets up the main user interface and layout."""
        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        mainLayout = QVBoxLayout(centralWidget)
        mainLayout.setSpacing(10)
        mainLayout.setContentsMargins(15, 15, 15, 15)

        self.titleLabel = QLabel("FitGirl Repack Verifier")
        self.titleLabel.setObjectName("titleLabel")
        self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mainLayout.addWidget(self.titleLabel)

        folderLayout = QHBoxLayout()
        self.folderPathEdit = QLineEdit()
        self.folderPathEdit.setPlaceholderText("Select repack folder")
        self.folderPathEdit.setReadOnly(True)
        self.browseButton = QPushButton("Browse...")
        self.browseButton.clicked.connect(self.selectFolder)
        folderLayout.addWidget(QLabel("Repack Folder:"))
        folderLayout.addWidget(self.folderPathEdit)
        folderLayout.addWidget(self.browseButton)
        mainLayout.addLayout(folderLayout)

        self.fileTable = QTableWidget()
        self.fileTable.setColumnCount(3)
        self.fileTable.setHorizontalHeaderLabels(["File", "Progress", "Status"])
        self.fileTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.fileTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.fileTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.fileTable.setColumnWidth(1, 150)
        self.fileTable.setColumnWidth(2, 100)
        self.fileTable.verticalHeader().hide()
        self.fileTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.fileTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        mainLayout.addWidget(self.fileTable)

        self.buttonStack = QStackedWidget()
        self.buttonStack.setFixedHeight(40)
        self.startButton = QPushButton("Start Verification")
        self.startButton.clicked.connect(self.startVerification)
        self.startButton.setFixedHeight(40)
        self.startButton.setEnabled(False)
        self.quitButton = QPushButton("Quit")
        self.quitButton.setObjectName("quitButton")
        self.quitButton.clicked.connect(self.close)
        self.quitButton.setFixedHeight(40)
        self.buttonStack.addWidget(self.startButton)
        self.buttonStack.addWidget(self.quitButton)
        mainLayout.addWidget(self.buttonStack)

        self.setStatusBar(QStatusBar(self))
        threadCountLabel = QLabel(f"Threads: {os.cpu_count() or 1}")
        self.statusBar().addPermanentWidget(threadCountLabel)
        self.statusBar().showMessage("Ready. Select a folder to begin.")

    def selectFolder(self):
        selectedFolder = QFileDialog.getExistingDirectory(self, "Select Repack Folder")
        if not selectedFolder:
            return

        self.folderPathEdit.setText(selectedFolder)
        md5Dir = os.path.join(selectedFolder, MD5_SUBFOLDER)
        manifestPath = os.path.join(md5Dir, MANIFEST_FILENAME)

        if not os.path.isdir(md5Dir) or not os.path.isfile(manifestPath):
            self.statusBar().showMessage(f"Error: Required folder/file structure not found.")
            self.clearFileList()
            self.adjustWindowSize()
            return

        self.statusBar().showMessage("Manifest found. Ready to verify.")
        self.populateFileList(manifestPath, selectedFolder)

    def clearFileList(self):
        """Resets the file list and internal task state."""
        self.startButton.setEnabled(False)
        self.tasks.clear()
        self.fileTable.setRowCount(0)

    def populateFileList(self, manifestPath, repackRootFolder):
        """Reads the manifest file and populates the UI table with tasks."""
        self.clearFileList()
        try:
            with open(manifestPath, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith(';')]
        except Exception as e:
            self.statusBar().showMessage(f"Error reading manifest: {e}")
            self.adjustWindowSize()
            return

        self.fileTable.setRowCount(len(lines))
        for i, line in enumerate(lines):
            parts = line.split('*', 1)
            if len(parts) != 2:
                continue

            expectedHash = parts[0].strip()
            relativePathCleaned = parts[1].strip().lstrip('.\\/')
            absolutePathToCheck = os.path.join(repackRootFolder, relativePathCleaned)
            self.tasks.append((absolutePathToCheck, expectedHash, relativePathCleaned))

            itemFile = QTableWidgetItem(relativePathCleaned)
            self.fileTable.setItem(i, 0, itemFile)

            progressBar = QProgressBar()
            progressBar.setValue(0)
            progressBar.setTextVisible(False)
            self.fileTable.setCellWidget(i, 1, progressBar)

            itemStatus = QTableWidgetItem("Pending")
            itemStatus.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fileTable.setItem(i, 2, itemStatus)

        if self.tasks:
            self.startButton.setEnabled(True)
            self.buttonStack.setCurrentWidget(self.startButton)

        self.adjustWindowSize()

    def adjustWindowSize(self):
        """Adjusts the main window height based on the number of files."""
        MAX_ROWS_FOR_STRETCH = 20
        numRows = self.fileTable.rowCount()

        if numRows == 0:
            self.resize(*self.initialSize)
            return

        headerHeight = self.fileTable.horizontalHeader().height()
        rowHeight = self.fileTable.rowHeight(0) if numRows > 0 else 25
        frameHeight = self.fileTable.frameWidth() * 2

        otherWidgetsHeight = (self.titleLabel.height() +
                              self.folderPathEdit.parent().sizeHint().height() +
                              self.buttonStack.height() +
                              self.statusBar().height())

        mainLayout = self.centralWidget().layout()
        layoutMargins = mainLayout.contentsMargins()
        otherWidgetsHeight += layoutMargins.top() + layoutMargins.bottom()
        otherWidgetsHeight += mainLayout.spacing() * 3

        rowsToDisplay = min(numRows, MAX_ROWS_FOR_STRETCH)
        targetTableHeight = headerHeight + (rowsToDisplay * rowHeight) + frameHeight

        totalHeight = targetTableHeight + otherWidgetsHeight
        self.resize(self.initialSize[0], totalHeight)

    def startVerification(self):
        """Initializes and starts the background verification thread."""
        if not self.tasks:
            return

        self.setControlsEnabled(False)
        self.buttonStack.setCurrentWidget(self.quitButton)
        self.statusBar().showMessage("Verification in progress...")

        self.workerThread = QThread()
        self.controller = VerificationController(self.tasks)
        self.controller.moveToThread(self.workerThread)

        self.workerThread.started.connect(self.controller.run)
        self.controller.allFinished.connect(self.finalizeVerification)
        self.controller.fileProgress.connect(self.updateFileProgress)
        self.controller.fileFinished.connect(self.updateFileStatus)

        # Ensure a clean slate for connections.
        try:
            self.workerThread.finished.disconnect()
        except TypeError:
            pass  # No connections to disconnect.

        # Handle thread cleanup.
        self.controller.allFinished.connect(self.workerThread.quit)
        self.controller.allFinished.connect(self.controller.deleteLater)
        self.workerThread.finished.connect(self.workerThread.deleteLater)

        self.workerThread.start()

    def updateFileProgress(self, index, percentage):
        """Updates a specific progress bar."""
        progressBar = self.fileTable.cellWidget(index, 1)
        if isinstance(progressBar, QProgressBar):
            progressBar.setValue(percentage)

    def updateFileStatus(self, index, status, color):
        """Updates a files final status in the table."""
        self.fileTable.removeCellWidget(index, 1)

        statusItem = self.fileTable.item(index, 2)
        statusItem.setText(status)
        statusItem.setForeground(QBrush(color))
        statusItem.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

    def finalizeVerification(self, summary):
        """Handles the completion of the entire verification process."""
        ok = summary.get('ok', 0)
        issues = summary.get('failed', 0) + summary.get('missing', 0) + summary.get('error', 0)
        if issues == 0:
            msg = f"All {ok} files verified successfully! Time: {summary['time']:.2f}s"
        else:
            msg = f"Verification complete with {issues} issue(s). Time: {summary['time']:.2f}s"

        self.statusBar().showMessage(msg)
        self.setControlsEnabled(True)
        self.workerThread = None

    def setControlsEnabled(self, enabled):
        """Enables or disables UI controls during verification."""
        self.browseButton.setEnabled(enabled)
        self.startButton.setEnabled(False if not enabled else bool(self.tasks))
        if enabled and self.tasks:
            self.buttonStack.setCurrentWidget(self.startButton)
        else:
            self.buttonStack.setCurrentWidget(self.quitButton)

    def closeEvent(self, event):
        """Handles the window close event."""
        if self.workerThread and self.workerThread.isRunning():
            self.statusBar().showMessage("Stopping verification and exiting...")
            # Request the controller to stop all background hash calculations.
            if self.controller:
                self.controller.stop()
            # Signal the QThread to terminate its event loop.
            self.workerThread.quit()
            # Wait for the thread to finish cleanly before closing the window.
            self.workerThread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
