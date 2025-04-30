import sys
import os

# 프로젝트 루트 경로를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import shutil # shutil 임포트
# import tempfile # tempfile 임포트 제거
import collections # collections 임포트
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListView, QSplitter, QTableView,
    QHeaderView, QFileDialog, QMessageBox, QDesktopWidget # QStyle 제거
)
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem, QResizeEvent, QImage, QIcon # QIcon 추가
from PyQt5.QtCore import Qt, QModelIndex, QSize, QThread, pyqtSlot, QSortFilterProxyModel # QSortFilterProxyModel 추가
from image_processor import ScanWorker, RAW_EXTENSIONS, DuplicateGroupWithSimilarity
from typing import Optional, Dict, Any, List, Tuple # Tuple 임포트 추가
# import send2trash # send2trash 다시 임포트
from file.undo_manager import UndoManager, WINSHELL_AVAILABLE
from PIL import Image # Image만 임포트
# from PIL.ImageQt import ImageQt5 # ImageQt 관련 임포트 제거
# from PIL import Image, ImageQt # 이전 방식 주석 처리
# from PIL.ImageQt import ImageQt # 이전 방식 주석 처리
import rawpy # rawpy 임포트
import numpy as np # numpy 임포트
from log_setup import setup_logging # 로깅 설정 임포트
import uuid # 그룹 ID 생성을 위해 uuid 임포트
# --- 아래 설정 관련 임포트들은 main.py로 이동 ---
# import winshell 
# from win32com.client import Dispatch 
# import pythoncom 
# --- 설정 변수 정의 제거 (main.py로 이동) ---
# APP_NAME = ...
# COMPANY_NAME = ...
# ... (ICON_PATH, SCRIPT_PATH, PYTHON_EXE_PATH, SHORTCUT_NAME, SHORTCUT_PATH 등 모두 제거)
# --- 설정 변수 정의 끝 ---

# --- ICON_PATH 는 MainWindow 에서 직접 사용하므로 필요. main.py 에서 정의된 것을 사용하도록 수정 필요.
#     -> MainWindow 생성 시 전달하거나, main.py 에서 설정된 전역 변수를 참조하는 방식 고려.
#     -> 가장 간단하게는 main.py 와 동일한 방식으로 여기서도 계산 (코드 중복 발생)
ICON_PATH = os.path.join(project_root, "assets", "icon.ico")

# 스타일시트 정의
QSS = """
QMainWindow {
    background-color: #f0f0f0; /* 밝은 회색 배경 */
}

QFrame {
    border: 1px solid #d0d0d0; /* 연한 테두리 */
    border-radius: 5px;
}

QLabel {
    font-size: 10pt; /* 기본 폰트 크기 */
    padding: 5px;
}

QPushButton {
    background-color: #e0e0e0; /* 버튼 배경 */
    border: 1px solid #c0c0c0;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 10pt;
}

QPushButton:hover {
    background-color: #d5d5d5;
}

QPushButton:pressed {
    background-color: #c8c8c8;
}

QPushButton:disabled {
    background-color: #f5f5f5;
    color: #a0a0a0;
}

QTableView {
    border: 1px solid #d0d0d0;
    gridline-color: #e0e0e0;
    font-size: 9pt;
}

QHeaderView::section {
    background-color: #e8e8e8;
    padding: 4px;
    border: 1px solid #d0d0d0;
    font-size: 9pt;
}

QSplitter::handle {
    background-color: #d0d0d0;
}

QSplitter::handle:vertical {
    height: 5px;
}

QLabel#ImageLabel { /* ImageLabel 클래스에만 적용되도록 ID 선택자 또는 클래스 선택자 사용 고려 */
    background-color: #f0f0f0;
    border: 1px solid #cccccc;
    border-radius: 0px; /* 이미지 레이블은 각지게 */
}
"""

class ImageLabel(QLabel):
    """동적 크기 조절 및 비율 유지를 지원하는 이미지 레이블"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter) # 기본 정렬 설정
        self.setMinimumSize(100, 100) # 최소 크기 설정 (예시)

    def setPixmapFromFile(self, file_path: str) -> bool:
        """파일 경로로부터 Pixmap을 로드하고 원본을 저장합니다. RAW 및 TGA 지원 추가."""
        if not file_path or not os.path.exists(file_path):
            self._original_pixmap = None
            self.setText("File Not Found")
            return False

        pixmap = None
        file_ext = os.path.splitext(file_path)[1].lower()

        try:
            # RAW 또는 TGA 파일 처리
            if file_ext in RAW_EXTENSIONS or file_ext == '.tga':
                img_pil = None
                raw_obj = None
                qimage = None # QImage 객체 초기화
                try:
                    if file_ext in RAW_EXTENSIONS:
                        raw_obj = rawpy.imread(file_path)
                        rgb_array = raw_obj.postprocess(use_camera_wb=True)
                        img_pil = Image.fromarray(rgb_array)
                    elif file_ext == '.tga':
                        img_pil = Image.open(file_path)

                    if img_pil:
                        # PIL Image -> QImage 직접 변환
                        img_pil.draft(None, None) # Ensure image data is loaded
                        if img_pil.mode == "RGBA":
                            bytes_per_line = img_pil.width * 4
                            qimage = QImage(img_pil.tobytes("raw", "RGBA"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGBA8888)
                        elif img_pil.mode == "RGB":
                            bytes_per_line = img_pil.width * 3
                            qimage = QImage(img_pil.tobytes("raw", "RGB"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGB888)
                        else:
                            # 다른 모드는 RGB로 변환 시도
                            try:
                                rgb_img = img_pil.convert("RGB")
                                bytes_per_line = rgb_img.width * 3
                                qimage = QImage(rgb_img.tobytes("raw", "RGB"), rgb_img.width, rgb_img.height, bytes_per_line, QImage.Format_RGB888)
                                rgb_img.close() # 변환된 이미지 닫기
                            except Exception as convert_err:
                                print(f"Could not convert PIL image mode {img_pil.mode} to RGB for {file_path}: {convert_err}")
                                self.setText(f"Unsupported Image Mode\n{os.path.basename(file_path)}")
                                return False

                        if qimage and not qimage.isNull():
                            pixmap = QPixmap.fromImage(qimage)
                        else:
                             print(f"Failed to create QImage from PIL data for {file_path}")
                             self.setText(f"QImage Creation Failed\n{os.path.basename(file_path)}")
                             return False

                except rawpy.LibRawIOError as e:
                    print(f"rawpy I/O error for {file_path}: {e}")
                    self.setText(f"RAW Load Error (I/O)\n{os.path.basename(file_path)}")
                    return False
                except Exception as e:
                    print(f"Error processing {file_ext} file {file_path}: {e}")
                    self.setText(f"Cannot Load Image\n{os.path.basename(file_path)}")
                    return False
                finally:
                    if raw_obj:
                        raw_obj.close()
                    if img_pil and hasattr(img_pil, 'close'):
                         try:
                             img_pil.close()
                         except Exception as close_err:
                              print(f"Error closing PIL image {file_path}: {close_err}")

            # 기타 지원 형식 (Qt/Pillow 기본 로더 사용)
            else:
                pixmap = QPixmap(file_path)

            # Pixmap 유효성 검사 및 저장
            if pixmap and not pixmap.isNull():
                self._original_pixmap = pixmap
                self.updatePixmap()
                return True
            else:
                self._original_pixmap = None
                # pixmap 생성 실패 메시지는 위에서 처리됨
                if not (file_ext in RAW_EXTENSIONS or file_ext == '.tga'): # 일반 파일 로드 실패 시 메시지 설정
                     self.setText(f"Invalid Image File\n{os.path.basename(file_path)}")
                return False

        except Exception as e:
            print(f"Unexpected error in setPixmapFromFile for {file_path}: {e}")
            self._original_pixmap = None
            self.setText(f"Load Error\n{os.path.basename(file_path)}")
            return False

    def updatePixmap(self):
        """원본 Pixmap을 현재 레이블 크기에 맞게 스케일링하여 표시합니다."""
        if not self._original_pixmap:
            self.clear()
            # 필요 시 기본 텍스트 설정
            # self.setText("Image Area")
            return

        # 현재 레이블 크기 가져오기
        label_size = self.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            # 위젯 크기가 유효하지 않으면 스케일링 건너뛰기
             super().setPixmap(self._original_pixmap)
             return

        # 원본 비율 유지하며 스케일링
        scaled_pixmap = self._original_pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().setPixmap(scaled_pixmap) # QLabel의 setPixmap 직접 호출

    def resizeEvent(self, event: QResizeEvent):
        """위젯 크기가 변경될 때 호출됩니다."""
        self.updatePixmap() # 크기 변경 시 이미지 업데이트
        super().resizeEvent(event)

    def clear(self):
        """이미지와 원본 Pixmap을 초기화합니다."""
        self._original_pixmap = None
        super().clear()
        self.setText("Image Area") # 초기 텍스트 설정

# --- 사용자 정의 정렬 프록시 모델 ---
class SimilaritySortProxyModel(QSortFilterProxyModel):
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # --- 'Rank' 열 (인덱스 0) 또는 'Similarity' 열 (인덱스 3) 정렬 처리 --- 
        column = left.column()
        if column == 0: # 'Rank' 열
            left_data = self.sourceModel().data(left, Qt.UserRole + 6) # Rank 데이터는 Role +6
            right_data = self.sourceModel().data(right, Qt.UserRole + 6)
            # 'Rank' 열은 오름차순 (작은 번호 먼저)
            sort_order_multiplier = 1 
        elif column == 3: # 'Similarity' 열
            left_data = self.sourceModel().data(left, Qt.UserRole + 4)
            right_data = self.sourceModel().data(right, Qt.UserRole + 4)
            # 'Similarity' 열은 내림차순 (높은 퍼센트 먼저)
            sort_order_multiplier = -1 
        else:
            # 다른 열은 기본 정렬
            return super().lessThan(left, right)
            
        # 데이터 유효성 검사 및 숫자 비교 (기존 로직 유지)
        try:
            if left_data is None and right_data is None: return False
            if left_data is None: return True 
            if right_data is None: return False 
            return sort_order_multiplier * float(left_data) < sort_order_multiplier * float(right_data)
        except (ValueError, TypeError):
            return super().lessThan(left, right)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.undo_manager = UndoManager(self)
        self.scan_thread: Optional[QThread] = None
        self.scan_worker: Optional[ScanWorker] = None
        self.total_files_to_scan = 0 # 총 스캔할 파일 수 저장 변수
        self.group_representatives: Dict[str, str] = {} # {group_id: representative_file_path}
        self.duplicate_groups_data: Dict[str, List[Tuple[str, int]]] = {} # {group_id: [(member_path, similarity), ...]}
        self.last_acted_group_id: Optional[str] = None # 마지막으로 액션이 적용된 그룹 ID
        self.previous_selection_index: Optional[int] = None # 프록시 행 인덱스 저장용
        self.last_acted_representative_path: Optional[str] = None
        self.last_acted_member_path: Optional[str] = None

        # --- 초기화 시 경로 로깅 제거 ---
        # print(f"[MainWindow Init] Current Working Directory: {os.getcwd()}")
        # print(f"[MainWindow Init] Calculated ICON_PATH: {ICON_PATH}") 
        # --- 로깅 제거 끝 ---

        self.setWindowTitle("DuplicatePhotoFinderApp")

        # --- 아이콘 설정 (계산된 ICON_PATH 사용) ---
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        else:
             print(f"Warning: Application icon not found at {ICON_PATH}")
        # --- 아이콘 설정 끝 ---

        self.setGeometry(100, 100, 1100, 650) # 창 크기 조정 (1100x650)
        self.setStyleSheet(QSS) # 스타일시트 적용

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 상단 이미지 비교 영역 ---
        image_comparison_frame = QFrame()
        image_comparison_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
        image_comparison_layout = QHBoxLayout(image_comparison_frame)

        # 왼쪽 영역 (원본 이미지)
        left_panel_layout = QVBoxLayout()
        self.left_image_label = ImageLabel("Original Image Area") # ImageLabel 사용
        self.left_image_label.setFrameShape(QFrame.Box)
        # self.left_image_label.setMinimumSize(300, 200) # ImageLabel에서 설정
        left_panel_layout.addWidget(self.left_image_label, 1)
        self.left_info_label = QLabel("Image Info")
        self.left_info_label.setAlignment(Qt.AlignCenter)
        left_panel_layout.addWidget(self.left_info_label)
        left_button_layout = QHBoxLayout()
        self.left_move_button = QPushButton("Move")
        self.left_delete_button = QPushButton("Delete")
        left_button_layout.addWidget(self.left_move_button)
        left_button_layout.addWidget(self.left_delete_button)
        left_panel_layout.addLayout(left_button_layout)
        image_comparison_layout.addLayout(left_panel_layout)

        # 오른쪽 영역 (중복 이미지)
        right_panel_layout = QVBoxLayout()
        self.right_image_label = ImageLabel("Duplicate Image Area") # ImageLabel 사용
        self.right_image_label.setFrameShape(QFrame.Box)
        # self.right_image_label.setMinimumSize(300, 200) # ImageLabel에서 설정
        right_panel_layout.addWidget(self.right_image_label, 1)
        self.right_info_label = QLabel("Image Info")
        self.right_info_label.setAlignment(Qt.AlignCenter)
        right_panel_layout.addWidget(self.right_info_label)
        right_button_layout = QHBoxLayout()
        self.right_move_button = QPushButton("Move")
        self.right_delete_button = QPushButton("Delete")
        right_button_layout.addWidget(self.right_move_button)
        right_button_layout.addWidget(self.right_delete_button)
        right_panel_layout.addLayout(right_button_layout)
        image_comparison_layout.addLayout(right_panel_layout)

        # --- 하단 중복 목록 영역 ---
        duplicate_list_frame = QFrame()
        duplicate_list_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
        duplicate_list_layout = QVBoxLayout(duplicate_list_frame)

        # 스캔 버튼, Undo 버튼 및 상태 표시줄 영역
        scan_status_layout = QHBoxLayout()
        self.scan_folder_button = QPushButton("Scan Folder") # 버튼 참조 저장
        self.status_label = QLabel("Files scanned: 0 Duplicates found: 0")
        self.undo_button = QPushButton("Undo")
        self.undo_button.setEnabled(self.undo_manager.can_undo())
        scan_status_layout.addWidget(self.scan_folder_button)
        scan_status_layout.addWidget(self.status_label, 1)
        scan_status_layout.addWidget(self.undo_button)
        duplicate_list_layout.addLayout(scan_status_layout)

        # 중복 목록 테이블 뷰
        self.duplicate_table_view = QTableView()
        self.duplicate_table_model = QStandardItemModel() # 원본 데이터 모델
        self.duplicate_table_proxy_model = SimilaritySortProxyModel() # 프록시 모델 생성
        self.duplicate_table_proxy_model.setSourceModel(self.duplicate_table_model) # 소스 모델 연결

        # --- 테이블 헤더 '#' -> 'Rank', 초기 정렬 Rank 기준 ---
        self.duplicate_table_model.setHorizontalHeaderLabels(["Rank", "Representative", "Group Member", "Similarity", "Group ID"])
        
        # 테이블 뷰에는 *프록시* 모델 설정
        self.duplicate_table_view.setModel(self.duplicate_table_proxy_model) 
        self.duplicate_table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.duplicate_table_view.setSelectionBehavior(QTableView.SelectRows)
        self.duplicate_table_view.setSelectionMode(QTableView.SingleSelection)
        self.duplicate_table_view.setSortingEnabled(True) # 테이블 뷰 정렬 활성화

        # 열 너비 조정 (인덱스 조정)
        header = self.duplicate_table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # 'Rank' 열
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Representative
        header.setSectionResizeMode(2, QHeaderView.Stretch) # Group Member
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Similarity
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Group ID
        self.duplicate_table_view.setColumnHidden(4, True) # Group ID 열 숨기기 (인덱스 4)
        
        # 초기 정렬 설정 ('Rank' 오름차순)
        self.duplicate_table_view.sortByColumn(0, Qt.AscendingOrder)

        # 수직 헤더 숨기기
        self.duplicate_table_view.verticalHeader().setVisible(False)

        duplicate_list_layout.addWidget(self.duplicate_table_view)

        # 스플리터로 영역 나누기
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(image_comparison_frame)
        splitter.addWidget(duplicate_list_frame)
        # 초기 크기 비율 재조정 (상단 약 520, 하단 약 130 - 상단 80%)
        splitter.setSizes([520, 130])
        main_layout.addWidget(splitter)

        # --- 시그널 연결 ---
        self.scan_folder_button.clicked.connect(self.scan_folder) # scan_folder_button 참조 사용
        self.duplicate_table_view.clicked.connect(self.on_table_item_clicked)
        # 삭제 버튼 시그널 연결 (대상 이미지 지정)
        self.left_delete_button.clicked.connect(lambda: self.delete_selected_image('original'))
        self.right_delete_button.clicked.connect(lambda: self.delete_selected_image('duplicate'))
        # 이동 버튼 시그널 연결 (대상 이미지 지정)
        self.left_move_button.clicked.connect(lambda: self.move_selected_image('original'))
        self.right_move_button.clicked.connect(lambda: self.move_selected_image('duplicate'))
        self.undo_button.clicked.connect(self.undo_manager.undo_last_action)
        # UndoManager 시그널 연결 (반드시 임포트 이후)
        self.undo_manager.undo_status_changed.connect(self.update_undo_button_state)
        self.undo_manager.group_state_restore_needed.connect(self._handle_group_state_restore)

        self._center_window() # 창 중앙 정렬 메서드 호출

    def _center_window(self):
        """애플리케이션 창을 화면 중앙으로 이동시킵니다."""
        try:
            screen_geometry = QApplication.desktop().availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())
        except Exception as e:
            # QDesktopWidget 관련 오류 처리 (드물지만 발생 가능)
            print(f"Could not center window: {e}")

    def _update_image_info(self, image_label: ImageLabel, info_label: QLabel, file_path: str):
        """정보 레이블을 업데이트하고 ImageLabel에 Pixmap을 설정합니다."""
        # ImageLabel에 Pixmap 설정 시도 (이제 RAW/TGA 처리 가능)
        success = image_label.setPixmapFromFile(file_path)

        if success and image_label._original_pixmap: # 성공했고 원본 pixmap이 있으면 정보 업데이트
            pixmap = image_label._original_pixmap # 저장된 원본 사용
            try:
                file_size_kb = round(os.path.getsize(file_path) / 1024)
                img_format = os.path.splitext(file_path)[1].upper()[1:]
                filename = os.path.basename(file_path)
                # 원본 이미지 크기를 정보에 표시
                info_text = f"{img_format} {pixmap.width()} x {pixmap.height()} {file_size_kb} KB\n{filename}"
                info_label.setText(info_text)
            except FileNotFoundError:
                info_label.setText(f"File info error: Not found\n{os.path.basename(file_path)}")
            except Exception as e:
                print(f"Error getting file info: {e}")
                info_label.setText(f"Error getting info\n{os.path.basename(file_path)}")
        # Pixmap 로드 실패 시 메시지 처리 (setPixmapFromFile 내부에서 처리되거나 여기서 추가 처리)
        # elif file_path and not success: # 이미 setPixmapFromFile 에서 에러 텍스트 설정함
        #     pass # 이미 ImageLabel에 오류 메시지 표시됨
        elif file_path and not os.path.exists(file_path):
             # 파일 경로가 있지만 존재하지 않는 경우 (이 경우는 setPixmapFromFile 시작 시 처리됨)
             info_label.setText(f"File not found\n{os.path.basename(file_path)}")
        elif not file_path:
            # 파일 경로 자체가 없는 경우 (초기화 등)
            image_label.clear() # 명시적으로 clear 호출
            info_label.setText("Image Info")

    def browse_left_image(self):
        """왼쪽 'Browse' 버튼 클릭 시 파일 대화 상자를 열고 이미지를 로드합니다."""
        file_filter = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Original Image", "", file_filter)
        if file_path:
            self._update_image_info(self.left_image_label, self.left_info_label, file_path)

    def browse_right_image(self):
        """오른쪽 'Browse' 버튼 클릭 시 파일 대화 상자를 열고 이미지를 로드합니다."""
        file_filter = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Duplicate Image", "", file_filter)
        if file_path:
            self._update_image_info(self.right_image_label, self.right_info_label, file_path)

    def scan_folder(self):
        """폴더를 선택하고 백그라운드 스레드에서 중복 검사를 시작합니다."""
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.warning(self, "Scan in Progress", "A scan is already running.")
            return

        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder_path:
            # self.scan_folder_button.setEnabled(False) # 시작 시 비활성화
            # self.status_label.setText(f"Scanning folder: {folder_path}...") # 시작 메시지는 handle_scan_started에서 설정
            # QApplication.processEvents()

            # 스레드 및 워커 생성
            self.scan_thread = QThread()
            self.scan_worker = ScanWorker(folder_path)
            self.scan_worker.moveToThread(self.scan_thread)

            # 시그널 연결
            self.scan_thread.started.connect(self.scan_worker.run_scan)
            self.scan_worker.scan_started.connect(self.handle_scan_started) # scan_started 시그널 연결
            self.scan_worker.progress_updated.connect(self.update_scan_progress)
            self.scan_worker.scan_finished.connect(self.handle_scan_finished)
            self.scan_worker.error_occurred.connect(self.handle_scan_error)
            self.scan_worker.scan_finished.connect(self.cleanup_scan_thread)
            self.scan_worker.error_occurred.connect(self.cleanup_scan_thread)
            self.scan_thread.finished.connect(self.cleanup_scan_thread)

            # 스레드 시작
            self.scan_thread.start()
            self.scan_folder_button.setEnabled(False) # 스레드 시작 후 버튼 비활성화

    @pyqtSlot(int)
    def handle_scan_started(self, total_files: int):
        """스캔 시작 시 호출되어 총 파일 수를 저장하고 상태 메시지를 업데이트합니다."""
        self.total_files_to_scan = total_files
        self.status_label.setText(f"Scanning... 0 / {self.total_files_to_scan}")
        QApplication.processEvents() # 메시지 즉시 업데이트

    @pyqtSlot(int)
    def update_scan_progress(self, processed_count: int):
        """스캔 진행률 업데이트 슬롯"""
        if self.total_files_to_scan > 0:
            # "processed" 명시
            self.status_label.setText(f"Scanning... {processed_count} / {self.total_files_to_scan} files processed")
        else:
            self.status_label.setText(f"Scanning... Files processed: {processed_count}")

    @pyqtSlot(int, int, list)
    def handle_scan_finished(self, total_files: int, processed_count: int, duplicate_groups_with_similarity: DuplicateGroupWithSimilarity):
        """스캔 완료 시그널을 처리하여 결과를 테이블에 업데이트합니다."""
        # --- 수신된 데이터 로깅 제거 ---
        # print("--- [Debug] Received data in handle_scan_finished ---")
        # print(f"Total Files: {total_files}, Processed: {processed_count}")
        # print("Duplicate Groups Data:")
        # if not duplicate_groups_with_similarity:
        #     print("  No duplicates found.")
        # else:
        #     for rep, members in duplicate_groups_with_similarity:
        #         print(f"  Rep: {os.path.basename(rep)}")
        #         print(f"    Members: {[(os.path.basename(p), s) for p, s in members]}")
        # print("--- [Debug] End of received data ---\n")
        # --- 로깅 제거 끝 ---

        # 스캔 완료 상태 업데이트
        self.status_label.setText(f"Scan complete. Found {len(duplicate_groups_with_similarity)} duplicate groups in {processed_count}/{total_files} files.")

        # 내부 데이터 초기화
        self.duplicate_groups_data.clear()
        self.group_representatives.clear()
        self.duplicate_table_model.removeRows(0, self.duplicate_table_model.rowCount())

        # --- 유사도 기반 Rank 계산 로직 --- 
        all_duplicate_pairs = []
        temp_group_data = {}
        # 1. 모든 중복 쌍과 유사도(%) 수집
        for representative_path, members_with_similarity in duplicate_groups_with_similarity:
            if not members_with_similarity: continue
            group_id = str(uuid.uuid4()) # 임시 ID 부여 (나중에 테이블 채울 때 사용)
            temp_group_data[group_id] = {'rep': representative_path, 'members': []}
            for member_path, similarity in members_with_similarity:
                hash_bits = 64
                percentage_similarity = max(0, round((1 - similarity / hash_bits) * 100))
                # 대표/멤버 경로, 유사도%, 임시 그룹 ID 저장
                all_duplicate_pairs.append((representative_path, member_path, percentage_similarity, group_id, similarity))
                # 임시 그룹 데이터에도 멤버 추가 (나중에 Rank 와 함께 저장하기 위함)
                temp_group_data[group_id]['members'].append({'path': member_path, 'similarity': similarity, 'percentage': percentage_similarity, 'rank': -1}) # Rank 초기값 -1
                
        # 2. 유사도(%) 기준 내림차순 정렬
        all_duplicate_pairs.sort(key=lambda item: item[2], reverse=True)
        
        # 3. Rank 부여 및 최종 데이터 구조 생성
        ranked_group_data = {} # {group_id: [(member_path, similarity, rank), ...]}
        current_rank = 1
        for rep_path, mem_path, percent_sim, group_id, original_sim in all_duplicate_pairs:
            if group_id not in ranked_group_data:
                ranked_group_data[group_id] = []
            ranked_group_data[group_id].append((mem_path, original_sim, current_rank))
            # 임시 그룹 데이터에도 Rank 업데이트 (스냅샷용)
            for member_info in temp_group_data[group_id]['members']:
                if member_info['path'] == mem_path:
                    member_info['rank'] = current_rank
                    break
            current_rank += 1
            
        # 4. 내부 데이터 구조 업데이트 (대표 경로, 멤버+유사도+Rank)
        self.group_representatives.clear()
        self.duplicate_groups_data.clear()
        for group_id, data in temp_group_data.items():
             self.group_representatives[group_id] = data['rep']
             # 최종 저장 형식: (path, percentage_similarity, rank)
             self.duplicate_groups_data[group_id] = [(m['path'], m['percentage'], m['rank']) for m in data['members']]
        # --- Rank 계산 로직 끝 --- 

        # 그룹 데이터를 내부 구조에 저장하고 테이블 모델 채우기 (Rank 사용)
        # item_sequence_number = 1 # 시퀀스 번호 대신 Rank 사용
        # for representative_path, members_with_similarity in duplicate_groups_with_similarity: # 기존 루프 대신 ranked_group_data 사용
        
        # --- 테이블 채우기 로직 수정 (Rank 기반) ---
        # 정렬된 Rank 순서대로 테이블에 추가 (all_duplicate_pairs 사용)
        for rep_path, mem_path, percent_sim, group_id, original_sim in all_duplicate_pairs:
             rank = -1
             # 해당 멤버의 Rank 찾기 (이미 계산됨)
             for m_path, percent_sim_stored, r in self.duplicate_groups_data.get(group_id, []):
                  if m_path == mem_path:
                       rank = r
                       break
             if rank == -1: continue # 오류 방지

             # Rank 열 아이템 생성
             item_rank = QStandardItem(str(rank))
             item_rank.setTextAlignment(Qt.AlignCenter)
             item_rank.setData(rank, Qt.UserRole + 6) # Rank 정렬용 데이터 (Role +6)
             item_rank.setFlags(item_rank.flags() & ~Qt.ItemIsEditable)
             
             item_representative = QStandardItem(rep_path)
             item_member = QStandardItem(mem_path)
             
             similarity_text = f"{percent_sim}%"
             item_similarity = QStandardItem(similarity_text)
             item_similarity.setData(percent_sim, Qt.UserRole + 4)
             item_similarity.setTextAlignment(Qt.AlignCenter)
             item_group_id = QStandardItem(group_id)
             
             item_representative.setFlags(item_representative.flags() & ~Qt.ItemIsEditable)
             item_member.setFlags(item_member.flags() & ~Qt.ItemIsEditable)
             item_similarity.setFlags(item_similarity.flags() & ~Qt.ItemIsEditable)
             item_group_id.setFlags(item_group_id.flags() & ~Qt.ItemIsEditable)
             
             # 'Rank' 열 아이템 맨 앞에 추가
             self.duplicate_table_model.appendRow([item_rank, item_representative, item_member, item_similarity, item_group_id])
        # --- 테이블 채우기 로직 수정 끝 ---

        if self.duplicate_table_model.rowCount() > 0:
            # 초기 정렬이 Rank 기준이므로 첫 행 선택
            self.duplicate_table_view.selectRow(0)
            self.on_table_item_clicked(self.duplicate_table_proxy_model.index(0, 0))
        else:
            self.left_image_label.clear()
            self.left_info_label.setText("Image Info")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Info")

    @pyqtSlot(str)
    def handle_scan_error(self, error_message: str):
        """스캔 오류 처리 슬롯"""
        QMessageBox.critical(self, "Scan Error", error_message)
        self.status_label.setText("Scan failed.")
        # self.scan_folder_button.setEnabled(True) # cleanup_scan_thread에서 처리
        self.total_files_to_scan = 0 # 오류 시 총 파일 수 초기화

    @pyqtSlot()
    def cleanup_scan_thread(self):
        """스캔 스레드 및 워커 객체를 정리합니다."""
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait() # 스레드가 완전히 종료될 때까지 대기

        # 워커의 stop 메서드 호출 (선택적, 루프 중단용)
        if self.scan_worker:
            self.scan_worker.stop()

        # 객체 참조 해제 (메모리 누수 방지)
        # deleteLater()를 사용하면 이벤트 루프에서 안전하게 삭제
        if self.scan_worker:
            self.scan_worker.deleteLater()
        if self.scan_thread:
            self.scan_thread.deleteLater()

        self.scan_thread = None
        self.scan_worker = None
        print("Scan thread cleaned up.") # 확인용 로그
        self.scan_folder_button.setEnabled(True) # 버튼 활성화 보장
        self.total_files_to_scan = 0 # 스레드 정리 시 총 파일 수 초기화

    def on_table_item_clicked(self, index: QModelIndex):
        """테이블 뷰의 항목 클릭 시 상단 이미지 패널을 업데이트합니다."""
        if not index.isValid():
            return
            
        # --- 프록시 모델 인덱스를 소스 모델 인덱스로 변환 --- 
        source_index = self.duplicate_table_proxy_model.mapToSource(index)
        row = source_index.row()
        # --- 변환 끝 ---

        # --- 소스 모델에서 데이터 가져오기 --- 
        representative_path_item = self.duplicate_table_model.item(row, 1) 
        member_path_item = self.duplicate_table_model.item(row, 2) 
        group_id_item = self.duplicate_table_model.item(row, 4) 
        # --- 가져오기 끝 ---

        if representative_path_item and member_path_item and group_id_item:
            group_id = group_id_item.text()
            current_representative = self.group_representatives.get(group_id)
            selected_member = member_path_item.text()

            if current_representative:
                 self._update_image_info(self.left_image_label, self.left_info_label, current_representative)
                 self._update_image_info(self.right_image_label, self.right_info_label, selected_member)
            else:
                 print(f"Error: Representative not found for group {group_id}")
                 self.left_image_label.clear()
                 self.left_info_label.setText("Error: Group data missing")
                 self.right_image_label.clear()
                 self.right_info_label.setText("Error: Group data missing")

    def _get_selected_item_data(self, target_label: QLabel) -> Optional[Tuple[str, str]]:
        """현재 상단 패널에 표시된 이미지 경로와 그룹 ID를 반환합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if not selected_indexes:
            return None
        
        # --- 뷰 인덱스 -> 프록시 인덱스 -> 소스 인덱스 --- 
        proxy_index = selected_indexes[0]
        source_index = self.duplicate_table_proxy_model.mapToSource(proxy_index)
        selected_row = source_index.row()
        # --- 변환 끝 ---

        # --- 소스 모델에서 데이터 가져오기 --- 
        representative_item = self.duplicate_table_model.item(selected_row, 1)
        member_item = self.duplicate_table_model.item(selected_row, 2)
        group_id_item = self.duplicate_table_model.item(selected_row, 4) 
        # --- 가져오기 끝 ---

        if not (representative_item and member_item and group_id_item):
             return None

        group_id = group_id_item.text()
        representative_path = representative_item.text()
        member_path = member_item.text()

        # 어떤 버튼(왼쪽/오른쪽)이 눌렸는지 판단하여 해당 이미지 경로 반환
        if target_label is self.left_image_label:
             current_representative = self.group_representatives.get(group_id)
             if current_representative: 
                  return current_representative, group_id
             else: 
                  return None
        elif target_label is self.right_image_label:
             return member_path, group_id
        else:
            return None

    def delete_selected_image(self, target: str):
        """선택된 이미지를 휴지통으로 보내고 그룹 데이터를 업데이트합니다."""
        print(f"[Delete Entry] delete_selected_image called with target: {target}") 
        # --- 액션 전 상태 저장 (프록시 인덱스 및 경로) --- 
        try:
            print("[Delete Debug] Getting selected indexes...") # 추가 로그 1
            selected_proxy_indexes = self.duplicate_table_view.selectedIndexes()
            print("[Delete Debug] Got selected indexes.") # 추가 로그 2
            if not selected_proxy_indexes:
                print("[Delete Debug] No selection found.") # 추가 로그 3
                QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
                return
                
            selected_proxy_index = selected_proxy_indexes[0]
            print(f"[Delete Debug] Got proxy index: row={selected_proxy_index.row()}, col={selected_proxy_index.column()}") # 추가 로그 4
            source_index = self.duplicate_table_proxy_model.mapToSource(selected_proxy_index)
            print(f"[Delete Debug] Mapped to source index: row={source_index.row()}, col={source_index.column()}") # 추가 로그 5
            selected_row = source_index.row() # 소스 모델 행 (데이터 접근용)
            self.previous_selection_index = selected_proxy_index.row() # *** 프록시 행 인덱스 저장 ***
            print(f"[Delete Debug] Stored previous proxy index: {self.previous_selection_index}") # 추가 로그 6

            representative_item = self.duplicate_table_model.item(selected_row, 1) 
            print("[Delete Debug] Got representative item.") # 추가 로그 7
            member_item = self.duplicate_table_model.item(selected_row, 2) 
            print("[Delete Debug] Got member item.") # 추가 로그 8
            group_id_item = self.duplicate_table_model.item(selected_row, 4) 
            print("[Delete Debug] Got group_id item.") # 추가 로그 9

            if not (representative_item and member_item and group_id_item):
                print("[Delete Debug] Failed to get one or more items.") # 추가 로그 10
                QMessageBox.warning(self, "Warning", "Could not get item data.")
                self.previous_selection_index = None # 저장 실패 시 초기화
                return
                
            # 액션 대상 경로와 그룹 ID 가져오기
            original_representative_path = representative_item.text() 
            print(f"[Delete Debug] Got rep path: {original_representative_path}") # 추가 로그 11
            original_member_path = member_item.text() 
            print(f"[Delete Debug] Got mem path: {original_member_path}") # 추가 로그 12
            group_id = group_id_item.text() 
            print(f"[Delete Debug] Got group_id: {group_id}") # 추가 로그 13
            self.last_acted_group_id = group_id # 복원 시 그룹 식별용
            self.last_acted_representative_path = original_representative_path
            self.last_acted_member_path = original_member_path
            print(f"[Delete Debug] Stored last acted paths and group.") # 추가 로그 14
            
            target_label = self.left_image_label if target == 'original' else self.right_image_label
            image_path_to_delete = original_representative_path if target == 'original' else original_member_path
            print(f"[Delete Debug] Determined path to delete: {image_path_to_delete}") # 추가 로그 15
            # --- 저장 끝 ---

            # --- 복원을 위한 그룹 데이터 스냅샷 저장 --- 
            try:
                import copy # copy 모듈 임포트
                restore_snapshot_rep = self.group_representatives.get(group_id)
                # list of tuples -> deepcopy 필요
                restore_snapshot_members = copy.deepcopy(self.duplicate_groups_data.get(group_id, []))
                print(f"[Delete Debug] Created restore snapshot for group {group_id}. Rep: {os.path.basename(restore_snapshot_rep) if restore_snapshot_rep else 'None'}, Members: {len(restore_snapshot_members)}")
            except Exception as snap_err:
                print(f"[Delete Error] Failed to create restore snapshot: {snap_err}")
                restore_snapshot_rep = None
                restore_snapshot_members = None
                # 스냅샷 실패 시 진행 중단 (선택적이지만 안전함)
                QMessageBox.critical(self, "Error", "Failed to prepare for undo. Cannot proceed.")
                self.previous_selection_index = None
                self.last_acted_group_id = None
                return
            # --- 스냅샷 저장 끝 ---
            
            if group_id not in self.duplicate_groups_data or group_id not in self.group_representatives:
                print(f"[Delete Debug] Group data inconsistent for group_id: {group_id}")
                QMessageBox.critical(self, "Error", "Group data not found. Cannot process delete.")
                self.last_acted_group_id = None
                self.previous_selection_index = None
                return
            print("[Delete Debug] Group data consistency check passed.") # 추가 로그 17

            # 실행 취소 정보 준비
            representative_path_for_undo = self.group_representatives[group_id] 
            print("[Delete Debug] Got representative for undo.") # 추가 로그 18
            member_paths_for_undo = [path for path, _, _ in self.duplicate_groups_data[group_id]] 
            print("[Delete Debug] Got member paths for undo.") # 추가 로그 19
            all_original_paths_for_undo = [representative_path_for_undo] + member_paths_for_undo
            print("[Delete Debug] Prepared all paths for undo.") # 추가 로그 20

            # 1. 파일 삭제 시도 (UndoManager 사용)
            print("[Delete Debug] Attempting to delete file via UndoManager...") 
            if self.undo_manager.delete_file(image_path_to_delete, group_id, representative_path_for_undo, all_original_paths_for_undo, restore_snapshot_rep, restore_snapshot_members):
                print(f"[Delete Debug] File sent to trash (via UndoManager): {image_path_to_delete}")
                
                # 2. 내부 그룹 데이터에서 파일 제거
                print("[Delete Debug] Removing file from internal group data...")
                current_group_tuples = self.duplicate_groups_data[group_id]
                print(f"[Delete Debug] current_group_tuples before removal (len={len(current_group_tuples)}): {[(os.path.basename(p), s, sq) for p, s, sq in current_group_tuples[:5]]}...") # 일부만 로깅
                found_and_removed = False
                # --- 멤버 데이터 구조 변경 반영: (path, sim, rank) --- 
                for i, (path, _, _) in enumerate(current_group_tuples):
                    if path == image_path_to_delete:
                        print(f"[Delete Debug] Found item to remove at index {i}")
                        del current_group_tuples[i]
                        found_and_removed = True
                        print(f"[Delete Debug] Removed {os.path.basename(image_path_to_delete)} from group {group_id}. Remaining members: {len(current_group_tuples)}")
                        break
                # --- 수정 끝 ---
                if not found_and_removed:
                     print(f"[Delete Debug] Warning: {image_path_to_delete} not found in group data {group_id} upon delete.")
                print("[Delete Debug] Finished removing from internal group data.")

                # 3. 대표 이미지 처리
                print("[Delete Debug] Checking if representative needs update...")
                current_representative = self.group_representatives.get(group_id)
                if image_path_to_delete == current_representative:
                    print("[Delete Debug] Deleted item was the representative.")
                    if current_group_tuples: 
                        print("[Delete Debug] Setting new representative...")
                        # --- 새 대표 설정 및 멤버 목록에서 제거 (데이터 구조 변경 반영) ---
                        new_representative_path, _, _ = current_group_tuples[0] 
                        self.group_representatives[group_id] = new_representative_path
                        del current_group_tuples[0]
                        print(f"[Delete Debug] Group {group_id}: New representative set to {os.path.basename(new_representative_path)}")
                        # --- 수정 끝 ---
                        if not current_group_tuples:
                             print("[Delete Debug] Group became empty after setting new representative.")
                             pass # 아래에서 그룹 제거 로직 처리
                    else: 
                        print(f"[Delete Debug] Group {group_id} is now empty after deleting the only representative, removing group data.")
                        if group_id in self.duplicate_groups_data: del self.duplicate_groups_data[group_id]
                        if group_id in self.group_representatives: del self.group_representatives[group_id]
                        print("[Delete Debug] Group data removed.")
                else:
                    print("[Delete Debug] Deleted item was not the representative.")
                    
                # 4 & 5. 테이블 업데이트
                if group_id in self.duplicate_groups_data and self.duplicate_groups_data[group_id]: # 그룹이 존재하고 멤버가 남아있을 때만 업데이트
                     print(f"[Delete Debug] Calling _update_table_for_group for group {group_id}...")
                     self._update_table_for_group(group_id)
                     print(f"[Delete Debug] Finished _update_table_for_group for group {group_id}.")
                elif group_id not in self.duplicate_groups_data or not self.duplicate_groups_data.get(group_id): # 그룹 자체가 삭제되었거나 비었을 때
                     # 그룹 자체가 삭제된 경우 테이블에서 해당 그룹 ID 행 모두 제거
                     print(f"[Delete Debug] Group {group_id} removed or empty, removing rows from table model...")
                     rows_to_remove = []
                     for row in range(self.duplicate_table_model.rowCount()):
                          # --- Group ID 열 인덱스 변경 (4 -> 5) : 주의! _update_table_for_group 내부와 일치해야 함 ---
                          # -> _update_table_for_group 내부에서 그룹 ID 인덱스는 4가 맞음. 여기서도 4 사용.
                          item = self.duplicate_table_model.item(row, 4) # Group ID
                          if item and item.text() == group_id:
                               print(f"[Delete Debug] Found row {row} to remove for group {group_id}")
                               rows_to_remove.append(row)
                     # --- 수정 끝 ---
                     if rows_to_remove:
                         print(f"[Delete Debug] Removing rows: {rows_to_remove}")
                         for row in sorted(rows_to_remove, reverse=True):
                              self.duplicate_table_model.removeRow(row)
                         print("[Delete Debug] Rows removed from table model.")
                     else:
                         print("[Delete Debug] No rows found to remove for the deleted/empty group.")
                      
                # 6. UI 상태 업데이트
                print("[Delete Debug] Calling _update_ui_after_action...")
                self._update_ui_after_action()
                print("[Delete Debug] Delete action finished successfully.")
        except Exception as e:
            print(f"[Delete Error] Unhandled exception in delete setup: {e}")
            import traceback
            traceback.print_exc() # 오류 스택 트레이스 출력
            QMessageBox.critical(self, "Critical Error", f"An unexpected error occurred during delete setup: {e}")
            # 필요한 상태 초기화
            self.previous_selection_index = None
            self.last_acted_group_id = None
            self.last_acted_representative_path = None
            self.last_acted_member_path = None

    def move_selected_image(self, target: str):
        """선택된 이미지를 이동하고 그룹 데이터를 업데이트합니다."""
        print(f"[Move Entry] move_selected_image called with target: {target}")
        # --- 액션 전 상태 저장 (프록시 인덱스 및 경로) --- 
        selected_proxy_indexes = self.duplicate_table_view.selectedIndexes()
        if not selected_proxy_indexes:
            QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
            return
            
        selected_proxy_index = selected_proxy_indexes[0]
        source_index = self.duplicate_table_proxy_model.mapToSource(selected_proxy_index)
        selected_row = source_index.row() # 소스 모델 행
        self.previous_selection_index = selected_proxy_index.row() # *** 프록시 행 인덱스 저장 ***

        representative_item = self.duplicate_table_model.item(selected_row, 1)
        member_item = self.duplicate_table_model.item(selected_row, 2)
        group_id_item = self.duplicate_table_model.item(selected_row, 4) 

        if not (representative_item and member_item and group_id_item):
            QMessageBox.warning(self, "Warning", "Could not get item data.")
            self.previous_selection_index = None 
            return
            
        original_representative_path = representative_item.text()
        original_member_path = member_item.text()
        group_id = group_id_item.text()
        self.last_acted_group_id = group_id 
        self.last_acted_representative_path = original_representative_path
        self.last_acted_member_path = original_member_path

        image_path_to_move = original_representative_path if target == 'original' else original_member_path
        print(f"[Move Debug] Determined path to move: {image_path_to_move}")

        if not os.path.exists(image_path_to_move):
            QMessageBox.critical(self, "Error", f"File to move does not exist:\n{image_path_to_move}")
            self.previous_selection_index = None
            self.last_acted_group_id = None
            return

        # 1. 대상 폴더 선택
        destination_folder = QFileDialog.getExistingDirectory(self, f"Select Destination Folder for {os.path.basename(image_path_to_move)}")
        if not destination_folder:
            print("[Move Debug] Folder selection cancelled.")
            self.previous_selection_index = None # 사용자가 취소 시 상태 초기화
            self.last_acted_group_id = None
            return

        print(f"[Move Debug] Destination folder selected: {destination_folder}")

        # 2. 실행 취소를 위한 데이터 준비
        try:
            import copy
            # 현재 그룹 상태 스냅샷
            snapshot_rep = self.group_representatives.get(group_id)
            snapshot_members = copy.deepcopy(self.duplicate_groups_data.get(group_id, []))
            print(f"[Move Debug] Created restore snapshot for group {group_id}. Rep: {os.path.basename(snapshot_rep) if snapshot_rep else 'None'}, Members: {len(snapshot_members)}")
            
            # UndoManager 에 전달할 현재 대표 및 멤버 목록
            representative_path_for_undo = snapshot_rep # 스냅샷의 대표 사용
            member_paths_for_undo = [path for path, _, _ in snapshot_members]
            all_original_paths_for_undo = [representative_path_for_undo] + member_paths_for_undo
            print(f"[Move Debug] Prepared paths for undo: Rep={os.path.basename(representative_path_for_undo)}, All={len(all_original_paths_for_undo)}")
            
            # 3. 파일 이동 실행 (UndoManager 사용)
            print("[Move Debug] Attempting to move file via UndoManager...")
            if self.undo_manager.move_file(image_path_to_move, destination_folder, group_id, representative_path_for_undo, all_original_paths_for_undo, snapshot_rep, snapshot_members):
                print(f"[Move Debug] File moved successfully (via UndoManager): {image_path_to_move} -> {destination_folder}")
                
                # 4. 내부 데이터 업데이트
                print("[Move Debug] Removing moved file from internal group data...")
                current_group_tuples = self.duplicate_groups_data.get(group_id)
                if current_group_tuples is None:
                    print(f"[Move Warning] Group data for {group_id} already missing after move?")
                    self._update_ui_after_action() # UI 정리 시도
                    return
                    
                found_and_removed = False
                for i, (path, _, _) in enumerate(current_group_tuples):
                    if path == image_path_to_move:
                        print(f"[Move Debug] Found item to remove at index {i}")
                        del current_group_tuples[i]
                        found_and_removed = True
                        print(f"[Move Debug] Removed {os.path.basename(image_path_to_move)} from group {group_id}. Remaining members: {len(current_group_tuples)}")
                        break
                if not found_and_removed:
                     print(f"[Move Warning] {image_path_to_move} not found in group data {group_id} after move.")

                # 5. 대표 이미지 처리
                print("[Move Debug] Checking if representative needs update...")
                current_representative = self.group_representatives.get(group_id)
                if image_path_to_move == current_representative:
                    print("[Move Debug] Moved item was the representative.")
                    if current_group_tuples:
                        print("[Move Debug] Setting new representative...")
                        new_representative_path, _, _ = current_group_tuples[0]
                        self.group_representatives[group_id] = new_representative_path
                        del current_group_tuples[0] # 새 대표는 멤버 목록에서 제거
                        print(f"[Move Debug] Group {group_id}: New representative set to {os.path.basename(new_representative_path)}")
                        if not current_group_tuples:
                             print("[Move Debug] Group became empty after setting new representative.")
                             # 그룹 제거는 아래 로직에서 처리
                    else:
                        print(f"[Move Debug] Group {group_id} is now empty after moving the only representative, removing group data.")
                        if group_id in self.duplicate_groups_data: del self.duplicate_groups_data[group_id]
                        if group_id in self.group_representatives: del self.group_representatives[group_id]
                        print("[Move Debug] Group data removed.")
                else:
                    print("[Move Debug] Moved item was not the representative.")
                    if not current_group_tuples:
                        # 대표가 아닌 마지막 멤버가 이동된 경우
                        print(f"[Move Debug] Last member moved from group {group_id}. Removing group data.")
                        if group_id in self.duplicate_groups_data: del self.duplicate_groups_data[group_id]
                        if group_id in self.group_representatives: del self.group_representatives[group_id]
                        print("[Move Debug] Group data removed.")

                # 6. 테이블 및 UI 업데이트
                if group_id in self.duplicate_groups_data and self.duplicate_groups_data[group_id]: # 그룹이 존재하고 멤버가 남아있을 때만 테이블 업데이트
                     print(f"[Move Debug] Calling _update_table_for_group for group {group_id}...")
                     self._update_table_for_group(group_id)
                     print(f"[Move Debug] Finished _update_table_for_group for group {group_id}.")
                elif group_id not in self.duplicate_groups_data or not self.duplicate_groups_data.get(group_id): # 그룹 자체가 삭제되었거나 비었을 때
                     print(f"[Move Debug] Group {group_id} removed or empty, removing rows from table model...")
                     rows_to_remove = []
                     for row in range(self.duplicate_table_model.rowCount()):
                          item = self.duplicate_table_model.item(row, 4) # Group ID
                          if item and item.text() == group_id:
                               print(f"[Move Debug] Found row {row} to remove for group {group_id}")
                               rows_to_remove.append(row)
                     if rows_to_remove:
                         print(f"[Move Debug] Removing rows: {rows_to_remove}")
                         for row in sorted(rows_to_remove, reverse=True):
                              self.duplicate_table_model.removeRow(row)
                         print("[Move Debug] Rows removed from table model.")
                     else:
                         print("[Move Debug] No rows found to remove for the deleted/empty group.")

                print("[Move Debug] Calling _update_ui_after_action...")
                self._update_ui_after_action()
                print("[Move Debug] Move action finished successfully.")
            else:
                # 이동 실패 시 (UndoManager 에서 메시지 표시되었을 수 있음)
                print(f"[Move Error] UndoManager reported failure moving {image_path_to_move}")
                # 실패 시 상태 초기화 필요할 수 있음 (예: 선택 복구)
                self.previous_selection_index = None
                self.last_acted_group_id = None
                # _update_ui_after_action() # UI 업데이트는 불필요할 수 있음

        except Exception as e:
            print(f"[Move Error] Failed to move file {image_path_to_move}. Error: {e}")
            QMessageBox.critical(self, "Move Error", f"Failed to move file:\n{os.path.basename(image_path_to_move)}\nError: {e}")
            # 실패 시 상태 초기화 필요할 수 있음 (예: 선택 복구)
            self.previous_selection_index = None
            self.last_acted_group_id = None

    def update_undo_button_state(self, enabled: bool):
        """Undo 버튼의 활성화 상태를 업데이트하는 슬롯"""
        self.undo_button.setEnabled(enabled)

    def _update_table_for_group(self, group_id: str):
        """주어진 group_id에 해당하는 테이블 행들을 업데이트합니다 (Rank 및 유사도 포함)."""
        print(f"[UpdateTable Debug] Updating table for group_id: {group_id}") # 로그 1
        # 1. 해당 group_id의 모든 행 제거 (소스 모델 기준)
        rows_to_remove = []
        print(f"[UpdateTable Debug] Searching rows to remove...") # 로그 2
        for row in range(self.duplicate_table_model.rowCount()):
            # --- Group ID 열 인덱스 변경 (4 -> 5) : 주의! 이 함수 외부와 일치해야 함 ---
            # -> 그룹 ID는 이제 4번 인덱스가 맞음 (0:#, 1:Rep, 2:Mem, 3:Sim, 4:GroupID)
            item = self.duplicate_table_model.item(row, 4) 
            if item and item.text() == group_id:
                rows_to_remove.append(row)
        print(f"[UpdateTable Debug] Found rows to remove: {rows_to_remove}") # 로그 3

        if rows_to_remove:
            print(f"[UpdateTable Debug] Removing rows: {rows_to_remove}") # 로그 4
            for row in sorted(rows_to_remove, reverse=True):
                self.duplicate_table_model.removeRow(row)
            print(f"[UpdateTable Debug] Finished removing rows.") # 로그 5
        else:
            print(f"[UpdateTable Debug] No existing rows found for group {group_id}.")

        # 2. 업데이트된 그룹 정보로 새 행 추가
        if group_id in self.duplicate_groups_data:
            representative = self.group_representatives.get(group_id)
            # --- Rank 포함된 멤버 데이터 가져오기 --- 
            members_data = self.duplicate_groups_data[group_id]
            print(f"[UpdateTable Debug] Preparing to add new rows. Rep: {os.path.basename(representative) if representative else 'None'}, Members count: {len(members_data)}") # 로그 6
            
            if representative and members_data: 
                # --- Rank 데이터 언패킹 및 사용 --- 
                for member_path, similarity, rank in members_data:
                    print(f"[UpdateTable Debug] Processing member: {os.path.basename(member_path)}, Seq: {rank}") # 로그 7
                    if representative == member_path: continue 
                        
                    # 'Rank' 열 아이템 생성
                    item_rank = QStandardItem(str(rank))
                    item_rank.setTextAlignment(Qt.AlignCenter)
                    item_rank.setData(rank, Qt.UserRole + 6) # Rank 정렬용 데이터 (Role +6)
                    item_rank.setFlags(item_rank.flags() & ~Qt.ItemIsEditable)
                    
                    item_representative = QStandardItem(representative)
                    item_member = QStandardItem(member_path)
                    
                    similarity_text = f"{similarity}%"
                    item_similarity = QStandardItem(similarity_text)
                    item_similarity.setData(similarity, Qt.UserRole + 4)
                    item_similarity.setTextAlignment(Qt.AlignCenter)
                    item_group_id = QStandardItem(group_id)
                    
                    item_representative.setFlags(item_representative.flags() & ~Qt.ItemIsEditable)
                    item_member.setFlags(item_member.flags() & ~Qt.ItemIsEditable)
                    item_similarity.setFlags(item_similarity.flags() & ~Qt.ItemIsEditable)
                    item_group_id.setFlags(item_group_id.flags() & ~Qt.ItemIsEditable)
                    
                    # 'Rank' 열 아이템 맨 앞에 추가하여 행 추가
                    row_items = [item_rank, item_representative, item_member, item_similarity, item_group_id]
                    print(f"[UpdateTable Debug] Appending row for seq {rank}...") # 로그 8
                    self.duplicate_table_model.appendRow(row_items)
                    print(f"[UpdateTable Debug] Row appended for seq {rank}.") # 로그 9
            else: 
                print(f"[UpdateTable Debug] No representative or member data found for group {group_id}, not adding rows.") # 로그 10
        else:
            print(f"[UpdateTable Debug] Group {group_id} not found in duplicate_groups_data, not adding rows.") # 로그 11
        print(f"[UpdateTable Debug] Finished updating table for group_id: {group_id}") # 로그 12

    def _update_ui_after_action(self):
        """테이블 및 이미지 패널 상태를 업데이트합니다.

        액션(삭제, 이동, 실행취소) 후 호출되어,
        액션이 적용된 그룹의 첫 번째 항목을 선택하려고 시도합니다.
        그룹이 사라진 경우 이전 선택 위치 또는 마지막 항목을 선택합니다.
        """
        next_row_to_select = -1
        # --- 행 수와 인덱스는 프록시 모델 기준 --- 
        new_proxy_row_count = self.duplicate_table_proxy_model.rowCount()

        if new_proxy_row_count > 0:
            if self.last_acted_group_id:
                for proxy_row in range(new_proxy_row_count):
                    # 프록시 인덱스 -> 소스 인덱스
                    source_index_group_id = self.duplicate_table_proxy_model.mapToSource(
                        self.duplicate_table_proxy_model.index(proxy_row, 4)
                    )
                    # 소스 모델에서 그룹 ID 아이템 가져오기
                    item = self.duplicate_table_model.item(source_index_group_id.row(), 4) 
                    if item and item.text() == self.last_acted_group_id:
                        next_row_to_select = proxy_row # 선택할 행은 프록시 행 인덱스
                        break
            if next_row_to_select == -1:
                 if self.previous_selection_index is not None:
                     # 이전 선택 인덱스도 프록시 기준이었어야 함 (아래 수정 필요)
                     # 우선 현재 프록시 행 수 내에서 유효한 값으로 조정
                     next_row_to_select = min(self.previous_selection_index, new_proxy_row_count - 1)
                 else:
                     next_row_to_select = 0
                     
            if 0 <= next_row_to_select < new_proxy_row_count:
                 # 선택 및 클릭 이벤트 발생은 프록시 인덱스 사용
                 self.duplicate_table_view.selectRow(next_row_to_select)
                 self.on_table_item_clicked(self.duplicate_table_proxy_model.index(next_row_to_select, 0))
        else:
            self.left_image_label.clear()
            self.left_info_label.setText("Image Info")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Info")
            
        self.last_acted_group_id = None
        # --- previous_selection_index 를 프록시 모델 기준으로 저장하도록 수정 필요 --- 
        # (delete/move/restore 함수에서 self.duplicate_table_view.selectedIndexes()[0].row() 사용)
        self.previous_selection_index = None 
        # --- 수정 필요 끝 ---

    def _handle_group_state_restore(self, action_details: dict):
        """UndoManager로부터 그룹 상태 복원 요청을 처리합니다."""
        # 액션 전 선택 상태 저장 (실행 취소 시에도 프록시 인덱스 사용)
        current_selection = self.duplicate_table_view.selectedIndexes()
        if current_selection:
            self.previous_selection_index = current_selection[0].row() # 프록시 행 저장
        else:
            self.previous_selection_index = None

        action_type = action_details.get('type')
        group_id = action_details.get('group_id')
        self.last_acted_group_id = group_id 

        if not group_id:
             print("[Restore Error] Group ID not found in action details.")
             return

        print(f"[MainWindow] Handling group state restore for group {group_id} (Action: {action_type})")

        if action_type == UndoManager.ACTION_DELETE or action_type == UndoManager.ACTION_MOVE:
            # --- action_details 에서 스냅샷 데이터 추출 --- 
            restore_snapshot_rep = action_details.get('snapshot_rep')
            restore_snapshot_members = action_details.get('snapshot_members')
            
            if restore_snapshot_rep is None or restore_snapshot_members is None:
                print(f"[Restore Error] Restore snapshot data is missing in action_details for group {group_id}. Cannot restore accurately.")
                # 스냅샷 없으면 복원 중단 또는 기본 처리 (예: 첫 행 선택)
                # 안전하게 중단하고 메시지 표시
                QMessageBox.warning(self, "Restore Warning", "Could not restore exact previous state due to missing data.")
                return 
                 
            # 스냅샷으로 그룹 데이터 복원
            self.group_representatives[group_id] = restore_snapshot_rep
            self.duplicate_groups_data[group_id] = restore_snapshot_members # 이미 deepcopy된 상태
            print(f"[MainWindow] Restored group {group_id} from snapshot. Rep: {os.path.basename(restore_snapshot_rep)}, Members: {len(restore_snapshot_members)}")
            
            # --- 스냅샷 사용 끝 ---

            # 테이블 업데이트 (소스 모델의 맨 끝에 행 추가됨)
            self._update_table_for_group(group_id)
            print("[Restore Debug] _update_table_for_group finished.") # 추가 로그 1
            
            # --- 정렬 먼저 적용 후, 복원된 항목 찾아 선택 --- 
            # 1. 기존 정렬 상태 다시 적용
            print("[Restore Debug] Getting current sort order...") # 추가 로그 2
            current_sort_column = self.duplicate_table_view.horizontalHeader().sortIndicatorSection()
            current_sort_order = self.duplicate_table_view.horizontalHeader().sortIndicatorOrder()
            print(f"[Restore Debug] Current sort: col={current_sort_column}, order={current_sort_order}") # 추가 로그 3
            print("[Restore Debug] Re-applying sort to proxy model...") # 추가 로그 4
            self.duplicate_table_proxy_model.sort(current_sort_column, current_sort_order)
            print("[Restore Debug] Sort re-applied.") # 추가 로그 5
            
            # 2. 정렬된 테이블에서 복원된 *정확한 항목* 찾기
            print("[Restore Debug] Getting target paths for search...") # 추가 로그 6
            target_rep_path = self.last_acted_representative_path
            target_mem_path = self.last_acted_member_path
            print(f"[Restore Debug] Target paths: Rep={os.path.basename(target_rep_path) if target_rep_path else 'None'}, Mem={os.path.basename(target_mem_path) if target_mem_path else 'None'}") # 추가 로그 7
            
            restored_proxy_row_index = -1
            if target_rep_path and target_mem_path: 
                print("[Restore Debug] Starting search loop for exact match...")
                for proxy_row in range(self.duplicate_table_proxy_model.rowCount()):
                     print(f"[Restore Loop Debug] Processing proxy_row: {proxy_row}") # 루프 시작 로그
                     # --- 열 인덱스 변경: Representative(1), Member(2) ---
                     proxy_index_rep = self.duplicate_table_proxy_model.index(proxy_row, 1)
                     print(f"[Restore Loop Debug] Got proxy_index_rep.") # 로그 A
                     source_index_rep = self.duplicate_table_proxy_model.mapToSource(proxy_index_rep)
                     print(f"[Restore Loop Debug] Mapped source_index_rep: row={source_index_rep.row()}, col={source_index_rep.column()}") # 로그 B
                     
                     proxy_index_mem = self.duplicate_table_proxy_model.index(proxy_row, 2)
                     print(f"[Restore Loop Debug] Got proxy_index_mem.") # 로그 C
                     source_index_mem = self.duplicate_table_proxy_model.mapToSource(proxy_index_mem)
                     print(f"[Restore Loop Debug] Mapped source_index_mem: row={source_index_mem.row()}, col={source_index_mem.column()}") # 로그 D
                     # --- 변경 끝 ---
                     
                     # 소스 모델에서 현재 행의 대표/멤버 경로 가져오기
                     current_rep_item = self.duplicate_table_model.item(source_index_rep.row(), 1)
                     print(f"[Restore Loop Debug] Got current_rep_item.") # 로그 E
                     current_mem_item = self.duplicate_table_model.item(source_index_mem.row(), 2)
                     print(f"[Restore Loop Debug] Got current_mem_item.") # 로그 F
                     
                     current_rep_path = current_rep_item.text() if current_rep_item else None
                     print(f"[Restore Loop Debug] Got current_rep_path: {os.path.basename(current_rep_path) if current_rep_path else 'None'}") # 로그 G
                     current_mem_path = current_mem_item.text() if current_mem_item else None
                     print(f"[Restore Loop Debug] Got current_mem_path: {os.path.basename(current_mem_path) if current_mem_path else 'None'}") # 로그 H
                     
                     if current_rep_path == target_rep_path and current_mem_path == target_mem_path:
                          print(f"[Restore Loop Debug] Found exact match at proxy_row {proxy_row}") # 로그 I
                          restored_proxy_row_index = proxy_row
                          break 
                print("[Restore Debug] Finished search loop.") # 루프 종료 로그
                          
            # 3. 찾은 행 선택, 스크롤 및 패널 업데이트 (EnsureVisible 사용)
            if restored_proxy_row_index != -1:
                self.duplicate_table_view.selectRow(restored_proxy_row_index)
                self.on_table_item_clicked(self.duplicate_table_proxy_model.index(restored_proxy_row_index, 0))
        else:
             print(f"[Restore Warning] Unhandled action type for restore: {action_type}")
             # 미지원 타입 등 처리 후, UI 상태 업데이트 (선택 초기화 등 필요시)
             # self._update_ui_after_action() # 필요 시 호출 

if __name__ == '__main__':
    # DPI 스케일링 활성화 
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    
    setup_logging() # 로깅 설정
    app = QApplication(sys.argv) # QApplication 생성
    app.setStyle('Fusion') # 스타일 적용
    
    # 애플리케이션 아이콘 설정 (선택적, main.py 에서도 설정됨)
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
        
    window = MainWindow() # 메인 윈도우 생성
    window.show() # 윈도우 표시
    sys.exit(app.exec_()) # 이벤트 루프 시작 