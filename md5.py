#!/usr/bin/env python3
import hashlib
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

# PyQt6 Imports
from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Constants
REPACK_MANIFEST_NAME = "fitgirl-bins.md5"
REPACK_MD5_SUBFOLDER = "MD5"
UNPACKED_MANIFEST_NAME = "fitgirl.md5"
UNPACKED_REDIST_SUBFOLDER = "_Redist"

# QT Stylesheet
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
QComboBox {
    border: 1px solid #555; border-radius: 4px; padding: 4px; min-width: 6em;
}
QComboBox:!editable, QComboBox::drop-down:editable { background: #444; }
QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: top right; width: 20px;
    border-left-width: 1px; border-left-color: #555; border-left-style: solid;
    border-top-right-radius: 3px; border-bottom-right-radius: 3px;
}
QComboBox QAbstractItemView {
    border: 2px solid #555; selection-background-color: #007acc; background-color: #3c3c3c;
}
QSpinBox {
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px;
    min-width: 4em;
    background-color: #3c3c3c;
}
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 16px;
    border-left: 1px solid #555;
}
QTableWidget {
    gridline-color: #444; background-color: #3c3c3c; border: 1px solid #555; border-radius: 4px;
}
QTableWidget::item { padding-left: 5px; border-bottom: 1px solid #444; }
QHeaderView::section { background-color: #444; padding: 4px; border: 1px solid #555; font-weight: bold; }
QPushButton {
    background-color: #007acc; color: #ffffff; border: none; padding: 8px 16px;
    border-radius: 4px; font-weight: bold;
}
QPushButton:hover { background-color: #008ae6; }
QPushButton:pressed { background-color: #006bb3; }
QPushButton:disabled { background-color: #404040; color: #888; }
QPushButton#quitButton { background-color: #c62828; }
QPushButton#quitButton:hover { background-color: #e53935; }
QPushButton#quitButton:pressed { background-color: #b71c1c; }
QPushButton#changeModeButton { background-color: #6c757d; }
QPushButton#changeModeButton:hover { background-color: #5a6268; }
QPushButton#changeModeButton:pressed { background-color: #545b62; }
QLineEdit { background-color: #3c3c3c; border: 1px solid #555; border-radius: 4px; padding: 4px; }
QProgressBar { border: 1px solid #555; border-radius: 4px; text-align: center; color: #f0f0f0; height: 18px; }
QProgressBar::chunk { background-color: #007acc; border-radius: 3px; margin: 1px; }
QStatusBar { font-size: 9pt; }
QLabel#titleLabel { font-size: 16pt; font-weight: bold; padding-bottom: 10px; }
QLabel#instructionLabel { font-size: 11pt; padding-bottom: 15px; }
"""

# Structs
class VerificationMode(Enum):
    REPACK = "Verify Repack (.bin files)"
    UNPACKED = "Verify Unpacked Game"

@dataclass
class FileTask:
    filepath: str
    expectedHash: str
    relativePath: str

# Core
def calculateMd5(
    filepath: str,
    blockSize: int = 655360,
    progressCallback: Optional[Callable[[int], None]] = None,
    isRunningCheck: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
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
                    currentPercentage = int((bytesRead / totalSize) * 100)
                    if currentPercentage > lastPercentage:
                        progressCallback(currentPercentage)
                        lastPercentage = currentPercentage
        if progressCallback and lastPercentage < 100:
            progressCallback(100)  # Ensure it finishes at 100%
        return md5.hexdigest()
    except FileNotFoundError:
        return None
    except IOError:
        return "IO_ERROR"

class VerifierThread(QThread):
    fileStarted = pyqtSignal(int)
    fileProgress = pyqtSignal(int, int)
    fileFinished = pyqtSignal(int, str, QColor)
    allFinished = pyqtSignal(dict)

    def __init__(self, tasks: List[FileTask], threadCount: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.tasks = tasks
        self.threadCount = threadCount
        self.isRunning = True
        self.executor: Optional[ThreadPoolExecutor] = None

    def run(self) -> None:
        summary = {"ok": 0, "failed": 0, "missing": 0, "error": 0, "total": len(self.tasks), "time": 0.0}
        startTime = time.perf_counter()
        
        self.executor = ThreadPoolExecutor(max_workers=self.threadCount)
        futures = {self.executor.submit(self._processFile, i, task): i for i, task in enumerate(self.tasks)}

        try:
            for future in as_completed(futures):
                if not self.isRunning:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    statusCode = future.result()
                    if statusCode and statusCode != "CANCELLED":
                        summary[statusCode.lower()] += 1
                except Exception:
                    pass
        finally:
            self.executor.shutdown(wait=True)
            endTime = time.perf_counter()
            summary["time"] = endTime - startTime
            self.allFinished.emit(summary)

    def _processFile(self, index: int, task: FileTask) -> str:
        if not self.isRunning:
            return "CANCELLED"

        self.fileStarted.emit(index)

        if not os.path.exists(task.filepath):
            self.fileFinished.emit(index, "MISSING", QColor("#ff5555"))
            return "MISSING"

        progressCallback = lambda p: self.fileProgress.emit(index, p) if self.isRunning else None
        isRunningCheck = lambda: self.isRunning

        actualMd5 = calculateMd5(
            task.filepath,
            progressCallback=progressCallback,
            isRunningCheck=isRunningCheck,
        )

        if not self.isRunning or actualMd5 == "CANCELLED":
            return "CANCELLED"
        if actualMd5 is None:
            self.fileFinished.emit(index, "MISSING", QColor("#ff5555"))
            return "MISSING"
        if actualMd5 == "IO_ERROR":
            self.fileFinished.emit(index, "I/O ERROR", QColor("#ff9900"))
            return "ERROR"

        if actualMd5.lower() == task.expectedHash.lower():
            self.fileFinished.emit(index, "OK", QColor("#55ff55"))
            return "OK"
        else:
            self.fileFinished.emit(index, "FAILED", QColor("#ff5555"))
            return "FAILED"

    def stop(self) -> None:
        self.isRunning = False


# Widgets
class StatusTableWidgetItem(QTableWidgetItem):
    
    class SortKey(Enum):
        ACTIVE = 0
        FAILED = 1
        OTHER = 2
        PENDING = 3
        OK = 4

    def __init__(self, text: str):
        super().__init__(text)
        self.sortKey = self.SortKey.PENDING

    def __lt__(self, other: 'StatusTableWidgetItem') -> bool:
        return self.sortKey.value < other.sortKey.value

    def setStatus(self, statusCode: str, displayText: Optional[str] = None) -> None:
        if displayText:
            self.setText(displayText)
        
        statusMap = {
            "OK": self.SortKey.OK,
            "FAILED": self.SortKey.FAILED,
            "MISSING": self.SortKey.FAILED,
            "I/O ERROR": self.SortKey.FAILED,
            "Verifying...": self.SortKey.ACTIVE
        }
        self.sortKey = statusMap.get(statusCode, self.SortKey.OTHER)


# GUI
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workerThread: Optional[VerifierThread] = None
        self.tasks: List[FileTask] = []
        self.verificationMode: Optional[VerificationMode] = None
        self.activeVerificationCount = 0

        self.setWindowTitle("FitGirl Repack & Game Verifier")
        self.setMinimumSize(800, 600)
        self.setWindowIcon(self._createAppIcon())

        self._setupUi()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready. Please select a verification mode to begin.")

    def _createAppIcon(self) -> QIcon:
        # Vector app icon bullshit, leave as-is
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
        return QIcon(pixmap)

    def _setupUi(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self._createWelcomePage()
        self._createMainPage()

    def _createWelcomePage(self) -> None:
        self.welcomePage = QWidget()
        layout = QVBoxLayout(self.welcomePage)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        title = QLabel("Welcome to FitGirl Verifier")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        instruction = QLabel("Please select a verification mode to continue:")
        instruction.setObjectName("instructionLabel")
        instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.welcomeModeSelector = QComboBox()
        self.welcomeModeSelector.setFixedWidth(300)
        self.welcomeModeSelector.addItem("Select Mode", userData=None)
        self.welcomeModeSelector.addItem(VerificationMode.REPACK.value, userData=VerificationMode.REPACK)
        self.welcomeModeSelector.addItem(VerificationMode.UNPACKED.value, userData=VerificationMode.UNPACKED)
        self.welcomeModeSelector.currentIndexChanged.connect(self._onWelcomeModeSelected)

        self.continueButton = QPushButton("Continue")
        self.continueButton.setFixedWidth(150)
        self.continueButton.setEnabled(False)
        self.continueButton.clicked.connect(self._switchToMainPage)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(instruction)
        layout.addWidget(self.welcomeModeSelector, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.continueButton, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)
        self.stack.addWidget(self.welcomePage)

    def _createMainPage(self) -> None:
        self.mainPage = QWidget()
        mainLayout = QVBoxLayout(self.mainPage)
        mainLayout.setSpacing(10)
        mainLayout.setContentsMargins(15, 15, 15, 15)

        topLayout = QHBoxLayout()
        self.modeInfoLabel = QLabel("Current Mode:")
        self.modeInfoLabel.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        
        self.threadCountLabel = QLabel("# of concurrent verifications:")
        self.threadCountSpinbox = QSpinBox()
        self.threadCountSpinbox.setRange(1, 50)
        self.threadCountSpinbox.setValue(os.cpu_count() or 1)
        self.threadCountSpinbox.setToolTip("Select number of files to check at the same time.\nDefaults to your system's logical core count.")
        
        changeModeButton = QPushButton("Change Mode")
        changeModeButton.setObjectName("changeModeButton")
        changeModeButton.clicked.connect(self._switchToWelcomePage)
        
        topLayout.addWidget(self.modeInfoLabel)
        topLayout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum))
        topLayout.addWidget(self.threadCountLabel)
        topLayout.addWidget(self.threadCountSpinbox)
        topLayout.addStretch()
        topLayout.addWidget(changeModeButton)
        mainLayout.addLayout(topLayout)

        folderLayout = QHBoxLayout()
        self.folderPathEdit = QLineEdit()
        self.folderPathEdit.setPlaceholderText("Select folder to verify")
        self.folderPathEdit.setReadOnly(True)
        self.browseButton = QPushButton("Browse...")
        self.browseButton.clicked.connect(self._onBrowseButtonClicked)
        folderLayout.addWidget(QLabel("Target Folder:"))
        folderLayout.addWidget(self.folderPathEdit)
        folderLayout.addWidget(self.browseButton)
        mainLayout.addLayout(folderLayout)

        self.fileTable = QTableWidget()
        self.fileTable.setColumnCount(3)
        self.fileTable.setHorizontalHeaderLabels(["File", "Progress", "Status"])
        self.fileTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.fileTable.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.fileTable.setColumnWidth(1, 150)
        self.fileTable.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.fileTable.setColumnWidth(2, 100)
        self.fileTable.verticalHeader().hide()
        self.fileTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.fileTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.fileTable.setSortingEnabled(False)
        mainLayout.addWidget(self.fileTable)

        self.buttonStack = QStackedWidget()
        self.buttonStack.setFixedHeight(40)
        self.startButton = QPushButton("Start Verification")
        self.startButton.clicked.connect(self._onStartButtonClicked)
        self.startButton.setFixedHeight(40)
        self.startButton.setEnabled(False)
        self.quitButton = QPushButton("Quit")
        self.quitButton.setObjectName("quitButton")
        self.quitButton.clicked.connect(self.close)
        self.quitButton.setFixedHeight(40)
        self.buttonStack.addWidget(self.startButton)
        self.buttonStack.addWidget(self.quitButton)
        mainLayout.addWidget(self.buttonStack)
        
        self.stack.addWidget(self.mainPage)

    def _onWelcomeModeSelected(self, index: int) -> None:
        isValidMode = self.welcomeModeSelector.itemData(index) is not None
        self.continueButton.setEnabled(isValidMode)
    
    def _switchToMainPage(self) -> None:
        index = self.welcomeModeSelector.currentIndex()
        selectedMode = self.welcomeModeSelector.itemData(index)
        if not isinstance(selectedMode, VerificationMode):
            return
            
        self.verificationMode = selectedMode
        self.modeInfoLabel.setText(f"Current Mode: {self.verificationMode.value}")
        self.stack.setCurrentWidget(self.mainPage)

    def _switchToWelcomePage(self) -> None:
        self._clearFileList()
        self.folderPathEdit.clear()
        self.startButton.setEnabled(False)
        self.buttonStack.setCurrentWidget(self.startButton)
        self.statusBar().showMessage("Ready. Please select a verification mode to begin.")
        self.stack.setCurrentWidget(self.welcomePage)

    def _onBrowseButtonClicked(self) -> None:
        if not self.verificationMode:
            return
        
        selectedFolder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not selectedFolder:
            return
            
        self.folderPathEdit.setText(selectedFolder)
        self._loadManifestFromFolder(selectedFolder)

    def _loadManifestFromFolder(self, folderPath: str) -> None:
        manifestPath, rootFolder = self._findManifest(folderPath)
        
        if not manifestPath or not rootFolder:
            self.statusBar().showMessage(
                f"Error: Required manifest file not found for '{self.verificationMode.value}' mode."
            )
            self._clearFileList()
            return
        
        tasks = self._parseManifest(manifestPath, rootFolder)
        if tasks is not None:
            self.tasks = tasks
            self._populateFileList()
            self.statusBar().showMessage("Manifest loaded successfully. Ready to verify.")

    def _findManifest(self, baseFolder: str) -> Tuple[Optional[str], Optional[str]]:
        if self.verificationMode == VerificationMode.REPACK:
            manifestPath = os.path.join(baseFolder, REPACK_MD5_SUBFOLDER, REPACK_MANIFEST_NAME)
            if os.path.isfile(manifestPath):
                return manifestPath, baseFolder
        
        elif self.verificationMode == VerificationMode.UNPACKED:
            for dirpath, _, _ in os.walk(baseFolder):
                if os.path.basename(dirpath) == UNPACKED_REDIST_SUBFOLDER:
                    manifestPath = os.path.join(dirpath, UNPACKED_MANIFEST_NAME)
                    if os.path.isfile(manifestPath):
                        gameRootFolder = os.path.dirname(dirpath)
                        return manifestPath, gameRootFolder
        
        return None, None

    def _parseManifest(self, manifestPath: str, rootFolder: str) -> Optional[List[FileTask]]:
        lines = []
        try:
            with open(manifestPath, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith(';')]
        except UnicodeDecodeError:
            self.statusBar().showMessage("UTF-8 decoding failed, trying legacy encoding (cp1252)...")
            try:
                with open(manifestPath, 'r', encoding='cp1252') as f:
                    lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith(';')]
                self.statusBar().showMessage("Successfully read manifest with legacy encoding.")
            except Exception as e:
                self.statusBar().showMessage(f"Error reading manifest with legacy encoding: {e}")
                return None
        except Exception as e:
            self.statusBar().showMessage(f"Error reading manifest: {e}")
            return None

        tasks: List[FileTask] = []
        manifestDir = os.path.dirname(manifestPath)
        for line in lines:
            parts = line.split('*', 1)
            if len(parts) != 2:
                continue
            
            expectedHash = parts[0].strip()
            relativePath = parts[1].strip().replace('/', os.sep)
            
            absolutePath = os.path.join(manifestDir, relativePath)
            
            tasks.append(FileTask(
                filepath=os.path.normpath(absolutePath),
                expectedHash=expectedHash,
                relativePath=relativePath,
            ))
        return tasks

    def _clearFileList(self) -> None:
        self.startButton.setEnabled(False)
        self.tasks.clear()
        self.fileTable.setRowCount(0)
    
    def _populateFileList(self) -> None:
        self.fileTable.setUpdatesEnabled(False)
        
        isUnpackedMode = self.verificationMode == VerificationMode.UNPACKED
        self.fileTable.setSortingEnabled(isUnpackedMode)
        
        self.fileTable.setRowCount(len(self.tasks))
        for i, task in enumerate(self.tasks):
            self.fileTable.setItem(i, 0, QTableWidgetItem(task.relativePath))
            statusItem = StatusTableWidgetItem("Pending")
            statusItem.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fileTable.setItem(i, 2, statusItem)
            
        self.fileTable.setUpdatesEnabled(True)
        if self.tasks:
            self.startButton.setEnabled(True)
            self.buttonStack.setCurrentWidget(self.startButton)

    def _onStartButtonClicked(self) -> None:
        if not self.tasks:
            return
            
        threadCount = self.threadCountSpinbox.value()
        self.activeVerificationCount = 0
        self._setControlsEnabled(False)
        self.buttonStack.setCurrentWidget(self.quitButton)
        self.statusBar().showMessage("Verification in progress...")

        self.workerThread = VerifierThread(self.tasks, threadCount)
        self.workerThread.fileStarted.connect(self._onFileStarted)
        self.workerThread.fileProgress.connect(self._onFileProgress)
        self.workerThread.fileFinished.connect(self._onFileFinished)
        self.workerThread.allFinished.connect(self._onAllFinished)
        self.workerThread.finished.connect(self.workerThread.deleteLater)
        self.workerThread.start()
    
    def _onFileStarted(self, index: int) -> None:
        self.activeVerificationCount += 1
        self._updateActiveCountStatus()
        
        progressBar = QProgressBar()
        progressBar.setValue(0)
        progressBar.setTextVisible(False)
        self.fileTable.setCellWidget(index, 1, progressBar)

        if self.verificationMode == VerificationMode.UNPACKED:
            statusItem = self.fileTable.item(index, 2)
            if isinstance(statusItem, StatusTableWidgetItem):
                statusItem.setStatus("Verifying...", displayText="Verifying...")

    def _onFileProgress(self, index: int, percentage: int) -> None:
        progressBar = self.fileTable.cellWidget(index, 1)
        if isinstance(progressBar, QProgressBar):
            progressBar.setValue(percentage)

    def _onFileFinished(self, index: int, status: str, color: QColor) -> None:
        self.activeVerificationCount -= 1
        self._updateActiveCountStatus()

        self.fileTable.removeCellWidget(index, 1)

        statusItem = self.fileTable.item(index, 2)
        if isinstance(statusItem, StatusTableWidgetItem):
            statusItem.setStatus(status, displayText=status)
        else:
            statusItem.setText(status)
        
        statusItem.setForeground(QBrush(color))
        statusItem.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        if status == "OK" and self.verificationMode == VerificationMode.UNPACKED:
            self.fileTable.hideRow(index)
            
    def _updateActiveCountStatus(self):
        active = self.activeVerificationCount
        threads = self.workerThread.threadCount if self.workerThread else 0
        if active > 0:
            self.statusBar().showMessage(f"Verifying... ({active}/{threads} active workers)")
        else:
            self.statusBar().showMessage("Verification in progress...")

    def _onAllFinished(self, summary: Dict) -> None:
        if self.verificationMode == VerificationMode.UNPACKED:
            self.fileTable.sortItems(2, Qt.SortOrder.AscendingOrder)
        
        okCount = summary.get('ok', 0)
        issueCount = summary.get('failed', 0) + summary.get('missing', 0) + summary.get('error', 0)
        wasCancelled = self.workerThread and not self.workerThread.isRunning
        
        if wasCancelled:
            msg = f"Verification cancelled. Time: {summary['time']:.2f}s"
        elif issueCount == 0 and okCount > 0:
            msg = f"All {okCount} files verified successfully! Time: {summary['time']:.2f}s"
        else:
            msg = f"Verification complete with {issueCount} issue(s). Time: {summary['time']:.2f}s"
            
        self.statusBar().showMessage(msg)
        self._setControlsEnabled(True)
        self.workerThread = None
        self.activeVerificationCount = 0

    def _setControlsEnabled(self, enabled: bool) -> None:
        self.browseButton.setEnabled(enabled)
        self.fileTable.setEnabled(enabled)
        self.threadCountSpinbox.setEnabled(enabled)
        
        canStart = enabled and bool(self.tasks)
        self.startButton.setEnabled(canStart)
        
        if canStart:
            self.buttonStack.setCurrentWidget(self.startButton)
        else:
            self.buttonStack.setCurrentWidget(self.quitButton)
    
    def closeEvent(self, event) -> None:
        if self.workerThread and self.workerThread.isRunning():
            self.statusBar().showMessage("Stopping verification and exiting...")
            self.workerThread.stop()
            self.workerThread.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
