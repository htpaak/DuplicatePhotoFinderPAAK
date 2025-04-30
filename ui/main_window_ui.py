import sys
import os

# 프로젝트 루트 경로 계산 (상대 경로가 아닌 절대 경로 기반으로 수정)
# 현재 파일 (main_window_ui.py) -> ui 폴더 -> 프로젝트 루트
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSplitter, QTableView,
    QHeaderView, QApplication # 필요한 위젯만 임포트
)
from PyQt5.QtGui import QStandardItemModel, QIcon
from PyQt5.QtCore import Qt

# MainWindow 는 타입 힌트용으로만 사용 (순환 참조 방지)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .main_window import MainWindow

from .image_label import ImageLabel
from .similarity_sort_proxy_model import SimilaritySortProxyModel

# ICON_PATH 및 QSS 정의 (main_window.py 에서 복사 및 수정)
ICON_PATH = os.path.join(project_root, "assets", "icon.ico")

QSS = """
QMainWindow {
    background-color: #f8f8f8; /* 더 밝고 부드러운 배경 */
}

QFrame {
    border: 1px solid #e0e0e0; /* 더 연한 테두리 */
    border-radius: 8px; /* 더 둥근 모서리 */
}

QLabel {
    font-size: 10pt;
    padding: 5px;
    color: #555; /* 약간 더 부드러운 텍스트 색상 */
}

QPushButton {
    background-color: #e0f2f1; /* 연한 민트 배경 */
    border: 1px solid #b2dfdb; /* 조금 더 진한 민트 테두리 */
    padding: 8px 15px; /* 패딩 증가 */
    border-radius: 8px; /* 더 둥근 모서리 */
    font-size: 10pt;
    color: #00796b; /* 진한 틸(Teal) 색상 텍스트 */
    font-weight: bold; /* 글자 두껍게 */
}

QPushButton:hover {
    background-color: #b2dfdb; /* 호버 시 조금 더 진하게 */
}

QPushButton:pressed {
    background-color: #a0cac5; /* 클릭 시 조금 더 어둡게 */
}

QPushButton:disabled {
    background-color: #f5f5f5;
    color: #bdbdbd; /* 비활성화 시 색상 조정 */
    border-color: #e0e0e0;
}

QTableView {
    border: 1px solid #e0e0e0; /* 프레임과 통일 */
    gridline-color: #f0f0f0; /* 격자선 더 연하게 */
    font-size: 9pt;
    selection-background-color: #b2dfdb; /* 선택 배경색 (민트) */
    selection-color: #004d40; /* 선택 텍스트 색 (어두운 틸) */
}

QHeaderView::section {
    background-color: #f5f5f5; /* 헤더 배경 (부드러운 회색) */
    padding: 5px;
    border: 1px solid #e0e0e0; /* 헤더 테두리 */
    font-size: 9pt;
    font-weight: bold;
    color: #616161; /* 헤더 텍스트 색상 (진한 회색) */
}

QSplitter::handle {
    background-color: #e0e0e0; /* 스플리터 핸들 색상 */
}

QSplitter::handle:vertical {
    height: 6px; /* 스플리터 핸들 두께 */
}

/* 특정 위젯에 대한 추가 스타일 */
QLabel#ImageLabel {
    background-color: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px; /* 이미지 레이블도 둥글게 */
}

QLabel#status_label { /* 상태 레이블 스타일 */
    color: #777;
    font-size: 9pt;
}

/* Undo 버튼 스타일 재정의 */
QPushButton#undo_button {
    background-color: #eeeeee; /* Undo 버튼 배경 (밝은 회색) */
    border: 1px solid #bdbdbd; /* Undo 버튼 테두리 */
    color: #424242; /* Undo 버튼 텍스트 (어두운 회색) */
}

QPushButton#undo_button:hover {
    background-color: #e0e0e0;
}

QPushButton#undo_button:pressed {
    background-color: #bdbdbd;
}

QPushButton#undo_button:disabled {
    background-color: #f5f5f5;
    color: #bdbdbd;
    border-color: #e0e0e0;
}
"""

def setup_ui(window: 'MainWindow'):
    """MainWindow의 UI 요소를 설정합니다."""

    # --- 아이콘 설정 (계산된 ICON_PATH 사용) ---
    if os.path.exists(ICON_PATH):
        window.setWindowIcon(QIcon(ICON_PATH))
    else:
         print(f"Warning: Application icon not found at {ICON_PATH}")
    # --- 아이콘 설정 끝 ---

    window.setStyleSheet(QSS) # 스타일시트 적용

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    main_layout = QVBoxLayout(central_widget)

    # --- 상단 이미지 비교 영역 ---
    image_comparison_frame = QFrame()
    image_comparison_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
    image_comparison_layout = QHBoxLayout(image_comparison_frame)

    # 왼쪽 영역 (원본 이미지)
    left_panel_layout = QVBoxLayout()
    window.left_image_label = ImageLabel("Original Image Area") # ImageLabel 사용, window 속성으로 할당
    window.left_image_label.setFrameShape(QFrame.Box)
    left_panel_layout.addWidget(window.left_image_label, 1)
    window.left_info_label = QLabel("Image Info") # window 속성으로 할당
    window.left_info_label.setAlignment(Qt.AlignCenter)
    left_panel_layout.addWidget(window.left_info_label)
    left_button_layout = QHBoxLayout()
    window.left_move_button = QPushButton("Move") # window 속성으로 할당
    window.left_delete_button = QPushButton("Delete") # window 속성으로 할당
    left_button_layout.addWidget(window.left_move_button)
    left_button_layout.addWidget(window.left_delete_button)
    left_panel_layout.addLayout(left_button_layout)
    image_comparison_layout.addLayout(left_panel_layout)

    # 오른쪽 영역 (중복 이미지)
    right_panel_layout = QVBoxLayout()
    window.right_image_label = ImageLabel("Duplicate Image Area") # ImageLabel 사용, window 속성으로 할당
    window.right_image_label.setFrameShape(QFrame.Box)
    right_panel_layout.addWidget(window.right_image_label, 1)
    window.right_info_label = QLabel("Image Info") # window 속성으로 할당
    window.right_info_label.setAlignment(Qt.AlignCenter)
    right_panel_layout.addWidget(window.right_info_label)
    right_button_layout = QHBoxLayout()
    window.right_move_button = QPushButton("Move") # window 속성으로 할당
    window.right_delete_button = QPushButton("Delete") # window 속성으로 할당
    right_button_layout.addWidget(window.right_move_button)
    right_button_layout.addWidget(window.right_delete_button)
    right_panel_layout.addLayout(right_button_layout)
    image_comparison_layout.addLayout(right_panel_layout)

    # --- 하단 중복 목록 영역 ---
    duplicate_list_frame = QFrame()
    duplicate_list_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
    duplicate_list_layout = QVBoxLayout(duplicate_list_frame)

    # 스캔 버튼, Undo 버튼 및 상태 표시줄 영역
    scan_status_layout = QHBoxLayout()
    window.scan_folder_button = QPushButton("Scan Folder") # window 속성으로 할당
    window.status_label = QLabel("Files scanned: 0 Duplicates found: 0") # window 속성으로 할당
    window.undo_button = QPushButton("Undo") # window 속성으로 할당
    window.undo_button.setObjectName("undo_button") # 객체 이름 설정
    window.undo_button.setEnabled(window.undo_manager.can_undo())
    scan_status_layout.addWidget(window.scan_folder_button)
    scan_status_layout.addWidget(window.status_label, 1)
    scan_status_layout.addWidget(window.undo_button)
    duplicate_list_layout.addLayout(scan_status_layout)

    # 중복 목록 테이블 뷰
    window.duplicate_table_view = QTableView() # window 속성으로 할당
    window.duplicate_table_model = QStandardItemModel() # 원본 데이터 모델, window 속성으로 할당
    window.duplicate_table_proxy_model = SimilaritySortProxyModel() # 프록시 모델 생성, window 속성으로 할당
    window.duplicate_table_proxy_model.setSourceModel(window.duplicate_table_model) # 소스 모델 연결

    # --- 테이블 헤더 '#' -> 'Rank', 초기 정렬 Rank 기준 ---
    window.duplicate_table_model.setHorizontalHeaderLabels(["Rank", "Representative", "Group Member", "Similarity", "Group ID"])
    
    # 테이블 뷰에는 *프록시* 모델 설정
    window.duplicate_table_view.setModel(window.duplicate_table_proxy_model) 
    window.duplicate_table_view.setEditTriggers(QTableView.NoEditTriggers)
    window.duplicate_table_view.setSelectionBehavior(QTableView.SelectRows)
    window.duplicate_table_view.setSelectionMode(QTableView.SingleSelection)
    window.duplicate_table_view.setSortingEnabled(True) # 테이블 뷰 정렬 활성화

    # 열 너비 조정 (인덱스 조정)
    header = window.duplicate_table_view.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # 'Rank' 열
    header.setSectionResizeMode(1, QHeaderView.Stretch) # Representative
    header.setSectionResizeMode(2, QHeaderView.Stretch) # Group Member
    header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Similarity
    header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Group ID
    window.duplicate_table_view.setColumnHidden(4, True) # Group ID 열 숨기기 (인덱스 4)
    
    # 초기 정렬 설정 ('Rank' 오름차순)
    window.duplicate_table_view.sortByColumn(0, Qt.AscendingOrder)

    # 수직 헤더 숨기기
    window.duplicate_table_view.verticalHeader().setVisible(False)

    duplicate_list_layout.addWidget(window.duplicate_table_view)

    # 스플리터로 영역 나누기
    splitter = QSplitter(Qt.Vertical)
    splitter.addWidget(image_comparison_frame)
    splitter.addWidget(duplicate_list_frame)
    # 초기 크기 비율 재조정 (상단 약 520, 하단 약 130 - 상단 80%)
    # window.height() 가 이 시점에는 유효하지 않을 수 있으므로 고정값 유지
    splitter.setSizes([520, 130]) 
    main_layout.addWidget(splitter)

    # 시그널 연결은 MainWindow.__init__ 에서 수행 