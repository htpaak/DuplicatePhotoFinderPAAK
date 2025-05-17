import sys
import os
import time
import platform
import subprocess
import traceback
import math
import re
import copy # 딥 카피를 위한 모듈 추가
from typing import Optional, List, Dict, Tuple, Any, Set, Union
import webbrowser # 웹 브라우저 모듈 임포트

# 프로젝트 루트 경로를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import shutil # shutil 임포트
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListView, QSplitter, QTableView,
    QHeaderView, QFileDialog, QMessageBox, QDesktopWidget # QStyle 제거
)
# QPixmap, QStandardItem, QResizeEvent 제거. QIcon 은 __main__ 에서만 사용
from PyQt5.QtGui import QStandardItemModel, QIcon, QStandardItem
# QSize 제거
from PyQt5.QtCore import Qt, QModelIndex, QThread, pyqtSlot
from image_processor import ScanWorker, RAW_EXTENSIONS, DuplicateGroupWithSimilarity
from file.undo_manager import UndoManager, WINSHELL_AVAILABLE
from log_setup import setup_logging # 로깅 설정 임포트
# import uuid # 그룹 ID 생성을 위해 uuid 임포트 제거

# --- 새로 분리된 클래스 및 UI 설정 함수 임포트 --- 
from ui.image_label import ImageLabel
from ui.similarity_sort_proxy_model import SimilaritySortProxyModel
from ui.main_window_ui import setup_ui # setup_ui 함수 임포트
from ui.file_action_handler import FileActionHandler # 파일 액션 핸들러 임포트
from ui.scan_result_processor import ScanResultProcessor # 스캔 결과 처리기 임포트
# --- 임포트 끝 ---

# --- ICON_PATH 및 QSS 정의 제거 (main_window_ui.py 로 이동) ---
# ICON_PATH = ...
# QSS = ...
# --- 제거 끝 ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.undo_manager = UndoManager(self)
        self.scan_thread: Optional[QThread] = None
        self.scan_worker: Optional[ScanWorker] = None
        self.total_files_to_scan = 0 # 총 스캔할 파일 수 저장 변수
        self.group_representatives: Dict[str, str] = {} # {group_id: representative_file_path}
        # 멤버 데이터 구조 변경: (path, percentage_similarity, rank)
        self.duplicate_groups_data: Dict[str, List[Tuple[str, int, int]]] = {} 
        self.last_acted_group_id: Optional[str] = None # 마지막으로 액션이 적용된 그룹 ID
        self.previous_selection_index: Optional[int] = None # 프록시 행 인덱스 저장용
        self.last_acted_representative_path: Optional[str] = None
        self.last_acted_member_path: Optional[str] = None
        # 선택된 항목 관리를 위한 변수 추가
        self.selected_items: List[str] = [] # 선택된 멤버 파일 경로 목록

        # --- 파일 액션 핸들러 인스턴스 생성 --- 
        self.file_action_handler = FileActionHandler(self)
        # --- 스캔 결과 처리기 인스턴스 생성 --- 
        self.scan_result_processor = ScanResultProcessor(self)
        # --- 핸들러/처리기 생성 끝 ---

        self.setWindowTitle("DuplicatePhotoFinderPAAK")
        self.setGeometry(100, 100, 1100, 650) # 창 크기 조정 (1100x650)

        # --- UI 설정 함수 호출 --- 
        setup_ui(self) # setup_ui 함수를 호출하여 UI 구성
        # --- UI 설정 끝 ---

        # --- 시그널 연결 (액션 버튼 핸들러 연결로 수정) --- 
        self.scan_folder_button.clicked.connect(self.scan_folder)
        self.duplicate_table_view.clicked.connect(self.on_table_item_clicked)
        self.left_delete_button.clicked.connect(lambda: self.file_action_handler.delete_selected_image('original'))
        self.right_delete_button.clicked.connect(lambda: self.file_action_handler.delete_selected_image('duplicate'))
        self.left_move_button.clicked.connect(lambda: self.file_action_handler.move_selected_image('original'))
        self.right_move_button.clicked.connect(lambda: self.file_action_handler.move_selected_image('duplicate'))
        self.undo_button.clicked.connect(self.undo_manager.undo_last_action)
        self.undo_manager.undo_status_changed.connect(self.update_undo_button_state)
        self.undo_manager.group_state_restore_needed.connect(self._handle_group_state_restore)
        
        # 새로 추가한 버튼들의 시그널 연결
        self.left_open_file_button.clicked.connect(lambda: self.open_selected_file('original'))
        self.right_open_file_button.clicked.connect(lambda: self.open_selected_file('duplicate'))
        self.left_open_folder_button.clicked.connect(lambda: self.open_parent_folder('original'))
        self.right_open_folder_button.clicked.connect(lambda: self.open_parent_folder('duplicate'))
        
        # 체크박스 클릭 이벤트를 처리하기 위한 시그널 연결
        self.duplicate_table_model.itemChanged.connect(self.on_checkbox_changed)
        
        # 일괄 작업 버튼 시그널 연결
        self.select_all_button.clicked.connect(self.select_all_items)
        self.select_none_button.clicked.connect(self.clear_selection)
        self.batch_delete_button.clicked.connect(self.delete_selected_items)
        self.batch_move_button.clicked.connect(self.move_selected_items)
        # --- 시그널 연결 끝 --- 

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

    def _update_image_info(self, image_label, info_label, file_path):
        """이미지 라벨과 정보 라벨을 업데이트합니다."""
        if not os.path.exists(file_path):
            image_label.clear()
            info_label.setText("File not found")
            return

        # 이미지 로드 시도
        loaded = image_label.load_path(file_path)
        
        # 파일 정보 업데이트
        try:
            # 파일 정보 가져오기
            file_size_kb = round(os.path.getsize(file_path) / 1024)
            file_ext = os.path.splitext(file_path)[1].upper()[1:]
            filename = os.path.basename(file_path)
            
            # 비디오 파일인 경우
            if image_label.is_video:
                # 비디오 길이 가져오기 시도
                from video_processor import VideoProcessor
                try:
                    duration = VideoProcessor.get_video_duration(file_path)
                    duration_text = f", {duration:.1f}초" if duration > 0 else ""
                except:
                    duration_text = ""
                
                # 비디오 정보 표시
                info_text = f"VIDEO {file_ext} {file_size_kb:,} KB{duration_text}\n{filename}"
                info_label.setText(info_text)
            
            # 이미지 파일인 경우
            elif image_label._original_pixmap:
                pixmap = image_label._original_pixmap
                # 원본 이미지 크기를 정보에 표시
                info_text = f"{file_ext} {pixmap.width()} x {pixmap.height()} {file_size_kb:,} KB\n{filename}"
                info_label.setText(info_text)
            
            # 그 외 경우 (pixmap이 없을 때)
            else:
                info_text = f"{file_ext} {file_size_kb:,} KB\n{filename}"
                info_label.setText(info_text)
                
        except FileNotFoundError:
            info_label.setText(f"File info error: Not found\n{os.path.basename(file_path)}")
        except Exception as e:
            print(f"Error getting file info: {e}")
            info_label.setText(f"Error getting info\n{os.path.basename(file_path)}")

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
            # 스레드 및 워커 생성
            self.scan_thread = QThread()
            # 하위폴더 포함 체크박스 상태를 ScanWorker에 전달
            include_subfolders = self.include_subfolders_checkbox.isChecked()
            self.scan_worker = ScanWorker(folder_path, include_subfolders)
            self.scan_worker.moveToThread(self.scan_thread)

            # 시그널 연결
            self.scan_thread.started.connect(self.scan_worker.run_scan)
            self.scan_worker.scan_started.connect(self.handle_scan_started) # scan_started 시그널 연결
            self.scan_worker.progress_updated.connect(self.update_scan_progress)
            # scan_finished 시그널을 ScanResultProcessor의 메서드에 연결
            self.scan_worker.scan_finished.connect(self.scan_result_processor.process_results)
            self.scan_worker.error_occurred.connect(self.handle_scan_error)
            # 스레드 정리 관련 연결은 유지
            self.scan_worker.scan_finished.connect(self.cleanup_scan_thread)
            self.scan_worker.error_occurred.connect(self.cleanup_scan_thread)
            self.scan_thread.finished.connect(self.cleanup_scan_thread)

            # 스레드 시작
            self.scan_thread.start()
            self.scan_folder_button.setEnabled(False) # 스레드 시작 후 버튼 비활성화

    def handle_scan_started(self, total_files: int):
        """스캔 시작 시 호출되어 총 파일 수를 저장하고 상태 메시지를 업데이트합니다."""
        self.total_files_to_scan = total_files
        
        # 하위폴더 포함 여부 메시지 추가
        include_subfolder_msg = " (including subfolders)" if self.include_subfolders_checkbox.isChecked() else ""
        
        # 총 파일 수가 0인 경우는 파일 수집 단계로 간주
        if total_files == 0:
            self.status_label.setText(f"Preparing to scan{include_subfolder_msg}...")
        else:
            self.status_label.setText(f"Scanning{include_subfolder_msg}... 0 / {self.total_files_to_scan}")
        
        QApplication.processEvents() # 메시지 즉시 업데이트

    def update_scan_progress(self, processed_count: int):
        """스캔 진행률 업데이트 슬롯"""
        # 하위폴더 포함 여부 메시지 추가
        include_subfolder_msg = " (including subfolders)" if self.include_subfolders_checkbox.isChecked() else ""
        
        # 음수 값은 폴더 검색 중임을 나타냄
        if processed_count < 0:
            if processed_count == -1:
                # 초기 폴더 검색 시작
                self.status_label.setText(f"Searching folders{include_subfolder_msg}...")
            else:
                # 폴더 검색 진행 중 (개수는 양수로 변환)
                folder_count = abs(processed_count)
                self.status_label.setText(f"Searching folders{include_subfolder_msg}... ({folder_count} folders processed)")
            QApplication.processEvents()  # UI 즉시 업데이트
            return
        
        # 일반적인 파일 스캔 진행 상황 표시
        if self.total_files_to_scan > 0:
            # "processed" 명시
            self.status_label.setText(f"Scanning{include_subfolder_msg}... {processed_count} / {self.total_files_to_scan} files processed")
        else:
            self.status_label.setText(f"Scanning... Files processed: {processed_count}")
        QApplication.processEvents()  # UI 즉시 업데이트

    def handle_scan_error(self, error_message: str):
        """스캔 오류 처리 슬롯"""
        QMessageBox.critical(self, "Scan Error", error_message)
        self.status_label.setText("Scan failed.")
        self.total_files_to_scan = 0 # 오류 시 총 파일 수 초기화

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
        print(f"[TableClick] Table item clicked: row={index.row()}, column={index.column()}")
        if not index.isValid():
            print("[TableClick] Invalid index")
            return
            
        # --- 프록시 모델 인덱스를 소스 모델 인덱스로 변환 --- 
        source_index = self.duplicate_table_proxy_model.mapToSource(index)
        row = source_index.row()
        # --- 변환 끝 ---

        # --- 소스 모델에서 데이터 가져오기 (인덱스 값 수정) --- 
        representative_path_item = self.duplicate_table_model.item(row, 2) 
        member_path_item = self.duplicate_table_model.item(row, 3) 
        similarity_item = self.duplicate_table_model.item(row, 4)
        group_id_item = self.duplicate_table_model.item(row, 5) 
        # --- 가져오기 끝 ---

        if representative_path_item and member_path_item and group_id_item:
            group_id = group_id_item.text()
            current_representative = self.group_representatives.get(group_id)
            selected_member = member_path_item.text()
            
            # 유사도 표시 로깅 (디버깅용)
            if similarity_item:
                similarity_text = similarity_item.text()
                similarity_data = similarity_item.data(Qt.UserRole + 4)
                print(f"유사도 텍스트: {similarity_text}, 데이터: {similarity_data}")

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

        # --- 소스 모델에서 데이터 가져오기 (인덱스 값 수정) --- 
        representative_item = self.duplicate_table_model.item(selected_row, 2)
        member_item = self.duplicate_table_model.item(selected_row, 3)
        group_id_item = self.duplicate_table_model.item(selected_row, 5) 
        # --- 가져오기 끝 ---

        if not (representative_item and member_item and group_id_item):
             return None

        group_id = group_id_item.text()
        representative_path = representative_item.text()
        member_path = member_item.text()

        # 어떤 버튼(왼쪽/오른쪽)이 눌렸는지 판단하여 해당 이미지 경로 반환
        if target_label is self.left_image_label:
             current_representative = self.group_representatives.get(group_id)
             return (current_representative, group_id) if current_representative else None
        elif target_label is self.right_image_label:
             return member_path, group_id
        else:
            return None

    def update_undo_button_state(self, enabled: bool):
        """Undo 버튼의 활성화 상태를 업데이트하는 슬롯"""
        self.undo_button.setEnabled(enabled)

    def _update_table_for_group(self, group_id: str):
        """주어진 group_id에 해당하는 테이블 행들을 업데이트합니다 (Rank 및 유사도 포함)."""
        print(f"[UpdateTable Debug] Updating table for group_id: {group_id}") # 로그 1
        
        # 기존 테이블 상태 확인
        before_source_rows = self.duplicate_table_model.rowCount()
        before_proxy_rows = self.duplicate_table_proxy_model.rowCount()
        print(f"[UpdateTable Debug] 기존 테이블 상태: 소스 행 수={before_source_rows}, 프록시 행 수={before_proxy_rows}")
        
        # 1. 해당 group_id의 모든 행 제거 (소스 모델 기준)
        rows_to_remove = []
        print(f"[UpdateTable Debug] Searching rows to remove...") # 로그 2
        for row in range(self.duplicate_table_model.rowCount()):
            # --- Group ID 열 인덱스 변경 (4 -> 5) : 주의! 이 함수 외부와 일치해야 함 ---
            # -> 그룹 ID는 이제 5번 인덱스로 변경 (0:Select, 1:Rank, 2:Rep, 3:Mem, 4:Sim, 5:GroupID)
            item = self.duplicate_table_model.item(row, 5) 
            if item and item.text() == group_id:
                rows_to_remove.append(row)
        print(f"[UpdateTable Debug] Found rows to remove: {rows_to_remove}") # 로그 3

        if rows_to_remove:
            print(f"[UpdateTable Debug] Removing rows: {rows_to_remove}") # 로그 4
            # 모든 연결된 시그널 일시 차단
            self.duplicate_table_model.blockSignals(True)
            self.duplicate_table_proxy_model.blockSignals(True)
            
            for row in sorted(rows_to_remove, reverse=True):
                self.duplicate_table_model.removeRow(row)
            
            # 시그널 복원
            self.duplicate_table_model.blockSignals(False)
            self.duplicate_table_proxy_model.blockSignals(False)
            
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
                # --- 테이블 모델 신호 잠시 차단 ---
                self.duplicate_table_model.blockSignals(True)
                self.duplicate_table_proxy_model.blockSignals(True)
                
                # --- Rank 순서대로 정렬하여 행 추가 ---
                # 먼저 Rank 기준으로 정렬
                sorted_members = sorted(members_data, key=lambda x: x[2])  # Rank(인덱스 2)로 정렬
                print(f"[UpdateTable Debug] Sorted members by rank: {[(os.path.basename(path), rank) for path, _, rank in sorted_members]}")
                
                # Rank 순서대로 테이블에 행 추가 (가장 작은 Rank부터)
                current_rank_to_row_map = {}  # 현재 테이블의 Rank -> 행 인덱스 매핑
                
                # 먼저 현재 테이블에서 Rank 값을 조사
                for row in range(self.duplicate_table_model.rowCount()):
                    rank_item = self.duplicate_table_model.item(row, 1)  # Rank는 1번 열
                    if rank_item:
                        try:
                            rank_value = int(rank_item.text())
                            current_rank_to_row_map[rank_value] = row
                        except ValueError:
                            pass
                
                # 테이블의 현재 행 수 (새 행을 추가할 때의 기본 위치)
                current_row_count = self.duplicate_table_model.rowCount()
                
                # 각 멤버에 대해 테이블에 행 추가
                for member_path, similarity, rank in sorted_members:
                    if representative == member_path: 
                        print(f"[UpdateTable Debug] Skipping representative: {os.path.basename(member_path)}")
                        continue
                    
                    print(f"[UpdateTable Debug] Adding row for: {os.path.basename(member_path)}, Rank: {rank}")
                    
                    # 체크박스 아이템 생성
                    item_checkbox = QStandardItem()
                    item_checkbox.setCheckable(True)
                    item_checkbox.setCheckState(Qt.Unchecked)
                    
                    # 'Rank' 열 아이템 생성
                    item_rank = QStandardItem(str(rank))
                    item_rank.setTextAlignment(Qt.AlignCenter)
                    item_rank.setData(rank, Qt.UserRole + 6) # Rank 정렬용 데이터 (Role +6)
                    item_rank.setFlags(item_rank.flags() & ~Qt.ItemIsEditable)
                    
                    # 대표 이미지 아이템
                    item_representative = QStandardItem(representative)
                    item_representative.setFlags(item_representative.flags() & ~Qt.ItemIsEditable)
                    
                    # 멤버 이미지 아이템
                    item_member = QStandardItem(member_path)
                    item_member.setFlags(item_member.flags() & ~Qt.ItemIsEditable)
                    
                    # 유사도 아이템
                    similarity_text = f"{similarity}%"
                    item_similarity = QStandardItem(similarity_text)
                    item_similarity.setData(similarity, Qt.UserRole + 4)
                    item_similarity.setTextAlignment(Qt.AlignCenter)
                    item_similarity.setFlags(item_similarity.flags() & ~Qt.ItemIsEditable)
                    
                    # 그룹 ID 아이템
                    item_group_id = QStandardItem(group_id)
                    item_group_id.setFlags(item_group_id.flags() & ~Qt.ItemIsEditable)
                    
                    # 행 아이템 생성
                    row_items = [item_checkbox, item_rank, item_representative, item_member, item_similarity, item_group_id]
                    
                    # 행을 추가할 위치 결정
                    # 현재 Rank보다 큰 Rank 값 중 가장 작은 것을 찾아 그 앞에 삽입
                    insert_position = current_row_count  # 기본값: 테이블의 맨 끝
                    
                    # 1. 현재 테이블에서 현재 Rank보다 큰 최소 Rank의 행을 찾아 그 앞에 삽입
                    higher_ranks = [r for r in current_rank_to_row_map.keys() if r > rank]
                    if higher_ranks:
                        min_higher_rank = min(higher_ranks)
                        insert_position = current_rank_to_row_map[min_higher_rank]
                        print(f"[UpdateTable Debug] 행 삽입: Rank {rank}를 Rank {min_higher_rank} 앞에 삽입 (행 인덱스: {insert_position})")
                    else:
                        # 현재 Rank보다 큰 Rank가 없으면, 유사한 Rank 행 뒤에 삽입
                        lower_ranks = [r for r in current_rank_to_row_map.keys() if r <= rank]
                        if lower_ranks:
                            max_lower_rank = max(lower_ranks)
                            insert_position = current_rank_to_row_map[max_lower_rank] + 1
                            print(f"[UpdateTable Debug] 행 삽입: Rank {rank}를 Rank {max_lower_rank} 뒤에 삽입 (행 인덱스: {insert_position})")
                        else:
                            print(f"[UpdateTable Debug] 행 삽입: Rank {rank}를 테이블 맨 끝에 삽입 (행 인덱스: {insert_position})")
                    
                    # 행 삽입
                    self.duplicate_table_model.insertRow(insert_position, row_items)
                    print(f"[UpdateTable Debug] 행 삽입 완료: 위치 {insert_position}, Rank {rank}")
                    
                    # 새 행 정보를 맵에 추가 (후속 삽입을 위해)
                    current_rank_to_row_map[rank] = insert_position
                    
                    # 삽입 위치 이후의 행 인덱스 업데이트
                    for r, row_idx in current_rank_to_row_map.items():
                        if row_idx >= insert_position and r != rank:
                            current_rank_to_row_map[r] = row_idx + 1
                    
                    # 현재 행 수 증가
                    current_row_count += 1
                
                # 테이블 모델 신호 차단 해제
                self.duplicate_table_model.blockSignals(False)
                self.duplicate_table_proxy_model.blockSignals(False)
                
                # 테이블에 추가된 행 수 확인
                print(f"[UpdateTable Debug] Final rows count: {self.duplicate_table_model.rowCount()}")
                
            else: 
                print(f"[UpdateTable Debug] No representative or member data found for group {group_id}, not adding rows.") # 로그 10
        else:
            print(f"[UpdateTable Debug] Group {group_id} not found in duplicate_groups_data, not adding rows.") # 로그 11
        
        # 현재 테이블 상태 확인
        after_source_rows = self.duplicate_table_model.rowCount()
        after_proxy_rows = self.duplicate_table_proxy_model.rowCount()
        print(f"[UpdateTable Debug] 현재 테이블 상태: 소스 행 수={after_source_rows}, 프록시 행 수={after_proxy_rows}")
        print(f"[UpdateTable Debug] 행 수 변화: 소스={after_source_rows-before_source_rows}, 프록시={after_proxy_rows-before_proxy_rows}")
        
        print(f"[UpdateTable Debug] Finished updating table for group_id: {group_id}") # 로그 12
        
        # 테이블 정렬 강제 적용 (Rank 열 기준으로 정렬)
        print(f"[UpdateTable Debug] Forcing sort by Rank column")
        self.duplicate_table_proxy_model.sort(1, Qt.AscendingOrder)
        self.duplicate_table_view.horizontalHeader().setSortIndicator(1, Qt.AscendingOrder)
        
        # 테이블 갱신 강제 적용
        self.duplicate_table_view.update()
        self.duplicate_table_view.repaint()  # 강제 다시 그리기 추가
        QApplication.processEvents()  # UI 이벤트 처리 보장
        
        # 프록시 모델 데이터 갱신 강제
        self.duplicate_table_proxy_model.invalidate()  # 프록시 모델 캐시 무효화
        self.duplicate_table_proxy_model.layoutChanged.emit()  # 레이아웃 변경 신호 강제 발생

    def _update_ui_after_action(self):
        """테이블 및 이미지 패널 상태를 업데이트합니다.

        액션(삭제, 이동, 실행취소) 후 호출되어,
        액션이 적용된 그룹의 첫 번째 항목을 선택하려고 시도합니다.
        그룹이 사라진 경우 이전 선택 위치 또는 마지막 항목을 선택합니다.
        """
        next_row_to_select = -1
        # --- 행 수와 인덱스는 프록시 모델 기준 --- 
        new_proxy_row_count = self.duplicate_table_proxy_model.rowCount()

        # 테이블이 비어있거나 더 이상 표시할 항목이 없는 경우
        if new_proxy_row_count == 0:
            print("[UI Update] Table is empty. Clearing image panels.")
            self.left_image_label.clear()
            self.left_info_label.setText("Image Area")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Area")
            
            # 이미지 캐시도 초기화
            self.left_image_label._original_pixmap = None
            self.right_image_label._original_pixmap = None
            
            # 테이블 모델도 명시적으로 초기화
            print("[UI Update] Ensuring table model is updated.")
            self.duplicate_table_view.reset()
            
            # 상태 메시지 업데이트 (선택된 항목 수가 0인 경우)
            if len(self.selected_items) == 0:
                self.status_label.setText("선택된 항목: 0개")
            
            self.last_acted_group_id = None
            self.previous_selection_index = None
            
            # 일괄 작업 버튼 상태 업데이트
            self._update_batch_buttons_state()
            return

        if self.last_acted_group_id:
            for proxy_row in range(new_proxy_row_count):
                # 프록시 인덱스 -> 소스 인덱스
                source_index_group_id = self.duplicate_table_proxy_model.mapToSource(
                    self.duplicate_table_proxy_model.index(proxy_row, 5)
                )
                # 소스 모델에서 그룹 ID 아이템 가져오기
                item = self.duplicate_table_model.item(source_index_group_id.row(), 5)
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
            print(f"[UI Update] Selecting row {next_row_to_select}")
            self.duplicate_table_view.selectRow(next_row_to_select)
            self.on_table_item_clicked(self.duplicate_table_proxy_model.index(next_row_to_select, 0))
        else:
            # 유효한 행을 선택할 수 없는 경우에도 UI 초기화
            print("[UI Update] Cannot select a valid row. Clearing image panels.")
            self.left_image_label.clear()
            self.left_info_label.setText("Image Area")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Area")
        
        self.last_acted_group_id = None
        # --- previous_selection_index 를 프록시 모델 기준으로 저장하도록 수정하겠습니다.
        # (delete/move/restore 함수에서 self.duplicate_table_view.selectedIndexes()[0].row() 사용)
        self.previous_selection_index = None 
        # --- 수정 필요 끝 ---
        
        # 테이블 업데이트 확인
        print(f"[UI Update] Final table state: {self.duplicate_table_model.rowCount()} source rows, {self.duplicate_table_proxy_model.rowCount()} proxy rows")

    def _handle_group_state_restore(self, action_details: dict):
        """UndoManager로부터 그룹 상태 복원 요청을 처리합니다."""
        print(f"[Restore Debug] 그룹 상태 복원 요청 수신: {action_details}")
        
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

        # 배치 작업에 대한 복원인지 확인
        is_batch_operation = action_type in ['batch_delete', 'batch_move']
        
        # 복원 전에 프록시 모델 필터 초기화 (모든 행이 표시되도록)
        # 검색 필터가 있는 경우 임시로 제거
        has_filter = bool(self.duplicate_table_proxy_model.filterRegExp().pattern())
        saved_filter = self.duplicate_table_proxy_model.filterRegExp()
        
        if has_filter:
            print("[Restore Debug] 임시로 필터 제거")
            self.duplicate_table_proxy_model.setFilterRegExp("")
        
        # 테이블 초기 상태 출력
        initial_source_rows = self.duplicate_table_model.rowCount()
        initial_proxy_rows = self.duplicate_table_proxy_model.rowCount()
        print(f"[Restore Debug] 초기 테이블 상태: 소스 행 수={initial_source_rows}, 프록시 행 수={initial_proxy_rows}")
        
        # 삭제 작업 복원인 경우
        if action_type == UndoManager.ACTION_DELETE or action_type == 'batch_delete':
            try:
                # 복원 스냅샷 정보 가져오기 
                restore_snapshot_rep = action_details.get('snapshot_rep')
                restore_snapshot_members = action_details.get('snapshot_members', [])
                
                print(f"[Restore Debug] 스냅샷 데이터 - 대표: {restore_snapshot_rep}, 멤버 수: {len(restore_snapshot_members)}")
                
                # 스냅샷으로 그룹 데이터 복원
                self.group_representatives[group_id] = restore_snapshot_rep
                self.duplicate_groups_data[group_id] = restore_snapshot_members
                
                # 데이터 복원 확인
                repr_exists = group_id in self.group_representatives
                members_exists = group_id in self.duplicate_groups_data
                print(f"[Restore Debug] 데이터 복원 확인 - 대표: {repr_exists}, 멤버: {members_exists}")
                
                # 복원 전 데이터 검증 - 정보 출력
                member_count = len(restore_snapshot_members)
                print(f"[Restore] 복원할 멤버 수: {member_count}, 대표 파일: {os.path.basename(restore_snapshot_rep)}")
                
                # 테이블 갱신 전 모든 시그널 차단
                self.duplicate_table_model.blockSignals(True)
                self.duplicate_table_proxy_model.blockSignals(True)
                self.duplicate_table_view.setUpdatesEnabled(False)
                
                # 테이블 갱신
                self._update_table_for_group(group_id)
                
                # 시그널 복원 및 강제 업데이트
                self.duplicate_table_model.blockSignals(False)
                self.duplicate_table_proxy_model.blockSignals(False)
                self.duplicate_table_view.setUpdatesEnabled(True)
                
                # 모든 이벤트 처리 보장
                QApplication.processEvents()
                
                # 테이블 정렬 강제 적용 - Rank 열(1번 인덱스)로 정렬
                print("[Restore] 테이블 정렬 적용 중 (Rank 열 기준)")
                self.duplicate_table_proxy_model.sort(1, Qt.AscendingOrder)
                self.duplicate_table_view.horizontalHeader().setSortIndicator(1, Qt.AscendingOrder)
                
                # 테이블 뷰 갱신 강제 적용
                self.duplicate_table_view.reset()
                self.duplicate_table_view.update()
                self.duplicate_table_view.repaint()
                
                # 복원 후 테이블 상태 확인
                source_rows = self.duplicate_table_model.rowCount()
                proxy_rows = self.duplicate_table_proxy_model.rowCount()
                print(f"[Restore] 복원 후 테이블 상태: 소스 행 수={source_rows}, 프록시 행 수={proxy_rows}")
                print(f"[Restore] 행 수 변화: 소스={source_rows-initial_source_rows}, 프록시={proxy_rows-initial_proxy_rows}")
                
                # 복원된 행 찾기
                print(f"[Restore Debug] 복원할 행 찾는 중 - 대표: {os.path.basename(restore_snapshot_rep)}, 멤버: {os.path.basename(restore_snapshot_members[0][0]) if restore_snapshot_members else 'None'}")
                next_row_to_select = None
                
                # 원본 모델에서 복원된 행 찾기
                for row in range(self.duplicate_table_model.rowCount()):
                    # 그룹 ID로 행 확인 (5번 열)
                    group_id_item = self.duplicate_table_model.item(row, 5)
                    if group_id_item and group_id_item.text() == group_id:
                        # 프록시 모델로 매핑
                        proxy_index = self.duplicate_table_proxy_model.mapFromSource(
                            self.duplicate_table_model.index(row, 0)
                        )
                        
                        # 프록시 인덱스가 유효한지 확인
                        if proxy_index.isValid():
                            next_row_to_select = proxy_index.row()
                            print(f"[Restore Debug] 복원된 행 찾음 - 소스 인덱스: {row}, 프록시 인덱스: {next_row_to_select}")
                            break
                        else:
                            print(f"[Restore Debug] 경고: 소스 인덱스 {row}에 해당하는 프록시 인덱스가 유효하지 않습니다!")
                
                # 복원된 행을 선택하거나 기본 선택 실행
                if next_row_to_select is not None:
                    print(f"[Restore Debug] 찾은 행 선택: {next_row_to_select}")
                    self.duplicate_table_view.selectRow(next_row_to_select)
                    # 선택된 행이 보이도록 스크롤
                    self.duplicate_table_view.scrollTo(
                        self.duplicate_table_proxy_model.index(next_row_to_select, 0),
                        QAbstractItemView.PositionAtCenter
                    )
                    
                    # 항목 클릭 이벤트 강제 발생 (이미지 패널 업데이트 위해)
                    self.on_table_item_clicked(self.duplicate_table_proxy_model.index(next_row_to_select, 0))
                else:
                    print("[Restore] 복원된 행을 찾을 수 없어 UI 업데이트를 호출합니다.")
                    # UI 업데이트 호출 전 한 번 더 테이블 갱신
                    self.duplicate_table_view.reset()
                    self.duplicate_table_proxy_model.invalidate()
                    QApplication.processEvents()
                    self._update_ui_after_action()
            except Exception as e:
                import traceback
                print(f"[Restore Error] {e}")
                traceback.print_exc()
                self._update_ui_after_action()
                
            # 저장했던 필터 다시 적용
            if has_filter:
                print("[Restore Debug] 필터 복원")
                self.duplicate_table_proxy_model.setFilterRegExp(saved_filter)
                
        # 이동 작업 복원인 경우 
        elif action_type == UndoManager.ACTION_MOVE or action_type == 'batch_move':
            # 이동은 삭제와 유사하게 처리하되, 특정 경로로의 이동 관련 처리 추가
            try:
                # 복원 스냅샷 정보 가져오기
                restore_snapshot_rep = action_details.get('snapshot_rep')
                restore_snapshot_members = action_details.get('snapshot_members', [])
                
                # 스냅샷으로 그룹 데이터 복원
                self.group_representatives[group_id] = restore_snapshot_rep
                self.duplicate_groups_data[group_id] = restore_snapshot_members
                
                # 테이블 갱신 전 모든 시그널 차단
                self.duplicate_table_model.blockSignals(True)
                self.duplicate_table_proxy_model.blockSignals(True)
                self.duplicate_table_view.setUpdatesEnabled(False)
                
                # 테이블 갱신
                self._update_table_for_group(group_id)
                
                # 시그널 복원 및 강제 업데이트
                self.duplicate_table_model.blockSignals(False)
                self.duplicate_table_proxy_model.blockSignals(False)
                self.duplicate_table_view.setUpdatesEnabled(True)
                
                # 테이블 뷰 갱신 강제 적용
                self.duplicate_table_view.reset()
                self.duplicate_table_view.update()
                self.duplicate_table_view.repaint()
                
                # 저장했던 필터 다시 적용
                if has_filter:
                    print("[Restore Debug] 필터 복원")
                    self.duplicate_table_proxy_model.setFilterRegExp(saved_filter)
                
                # UI 갱신
                self._update_ui_after_action()
            except Exception as e:
                print(f"[Restore Error] {e}")
                self._update_ui_after_action()
                
        print("[Restore] 그룹 상태 복원 완료")

    # --- 피드백 링크 여는 메서드 추가 ---
    def open_feedback_link(self):
        """피드백 링크 (GitHub Discussions)를 웹 브라우저에서 엽니다."""
        try:
            url = "https://github.com/htpaak/DuplicatePhotoFinderPAAK/discussions"
            webbrowser.open(url)
            print(f"Opened feedback URL: {url}")
        except Exception as e:
            print(f"Could not open feedback URL: {e}")
            QMessageBox.warning(self, "Error", f"Could not open the feedback page:\n{e}")
    # --- 메서드 추가 끝 ---

    # --- 파일 및 폴더 열기 메서드 추가 ---
    def open_selected_file(self, target: str):
        """선택된 이미지 파일을 시스템 기본 애플리케이션으로 엽니다."""
        try:
            target_label = self.left_image_label if target == 'original' else self.right_image_label
            item_data = self._get_selected_item_data(target_label)
            
            if not item_data:
                QMessageBox.warning(self, "Warning", "이미지를 선택하지 않았거나 선택한 항목에 대한 정보가 없습니다.")
                return
            
            file_path, _ = item_data
            
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "Warning", f"파일이 존재하지 않습니다: {file_path}")
                return
            
            # 시스템 기본 애플리케이션으로 파일 열기
            import subprocess
            
            # Windows 환경에서는 os.startfile 사용
            try:
                os.startfile(file_path)
                print(f"파일을 시스템 기본 애플리케이션으로 열었습니다: {file_path}")
            except AttributeError:
                # 다른 OS의 경우 대안 방법 사용 (macOS, Linux 등)
                try:
                    if sys.platform == 'darwin':  # macOS
                        subprocess.call(['open', file_path])
                    else:  # Linux 등
                        subprocess.call(['xdg-open', file_path])
                    print(f"파일을 시스템 기본 애플리케이션으로 열었습니다: {file_path}")
                except Exception as e:
                    print(f"파일 열기 실패: {e}")
                    QMessageBox.warning(self, "Error", f"파일을 열 수 없습니다: {e}")
        except Exception as e:
            print(f"파일 열기 오류: {e}")
            QMessageBox.warning(self, "Error", f"파일 열기 중 오류가 발생했습니다: {e}")

    def open_parent_folder(self, target: str):
        """선택된 이미지가 있는 폴더를 파일 탐색기에서 엽니다."""
        try:
            target_label = self.left_image_label if target == 'original' else self.right_image_label
            item_data = self._get_selected_item_data(target_label)
            
            if not item_data:
                QMessageBox.warning(self, "Warning", "이미지를 선택하지 않았거나 선택한 항목에 대한 정보가 없습니다.")
                return
            
            file_path, _ = item_data
            
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "Warning", f"파일이 존재하지 않습니다: {file_path}")
                return
            
            import subprocess
            
            # Windows 환경에서는 explorer /select 명령 사용
            if sys.platform == 'win32':
                try:
                    # 경로를 Windows 형식으로 변환 (백슬래시로 통일)
                    file_path = os.path.normpath(file_path)
                    # 명령어와 인자를 분리하여 실행 (셸 인젝션 방지 및 공백 포함 파일명 처리)
                    subprocess.run(['explorer', '/select,', file_path])
                    print(f"파일 선택 상태로 폴더를 열었습니다: {file_path}")
                except Exception as e:
                    print(f"파일 선택 폴더 열기 실패: {e}")
                    # 백업 방법: 간단하게 파일이 있는 디렉토리만 열기
                    try:
                        folder_path = os.path.dirname(file_path)
                        os.startfile(folder_path)
                        print(f"폴더만 열었습니다 (백업 방법): {folder_path}")
                    except Exception as e2:
                        print(f"폴더 열기 백업 방법도 실패: {e2}")
                    QMessageBox.warning(self, "Error", f"파일 선택 폴더 열기 중 오류가 발생했습니다: {e}")
            elif sys.platform == 'darwin':  # macOS
                try:
                    # macOS에서는 -R 옵션으로 파일 선택
                    subprocess.call(['open', '-R', file_path])
                    print(f"파일 선택 상태로 폴더를 열었습니다: {file_path}")
                except Exception as e:
                    print(f"파일 선택 폴더 열기 실패: {e}")
                    QMessageBox.warning(self, "Error", f"파일 선택 폴더 열기 중 오류가 발생했습니다: {e}")
            else:  # Linux 등
                try:
                    # Linux 환경에서 파일 선택을 위한 명령 (파일 매니저에 따라 다를 수 있음)
                    if os.path.exists('/usr/bin/nautilus'):  # GNOME/Nautilus
                        subprocess.call(['nautilus', '--select', file_path])
                    elif os.path.exists('/usr/bin/dolphin'):  # KDE/Dolphin
                        subprocess.call(['dolphin', '--select', file_path])
                    elif os.path.exists('/usr/bin/nemo'):  # Cinnamon/Nemo
                        subprocess.call(['nemo', file_path])
                    elif os.path.exists('/usr/bin/thunar'):  # XFCE/Thunar
                        subprocess.call(['thunar', os.path.dirname(file_path)])
                    else:
                        # 그 외의 경우 폴더만 열기
                        subprocess.call(['xdg-open', os.path.dirname(file_path)])
                    print(f"파일 선택 상태로 폴더를 열었습니다: {file_path}")
                except Exception as e:
                    print(f"파일 선택 폴더 열기 실패: {e}")
                    QMessageBox.warning(self, "Error", f"파일 선택 폴더 열기 중 오류가 발생했습니다: {e}")
        except Exception as e:
            print(f"폴더 열기 오류: {e}")
            QMessageBox.warning(self, "Error", f"폴더 열기 중 오류가 발생했습니다: {e}")
    # --- 메서드 추가 끝 ---

    def on_checkbox_changed(self, item):
        """체크박스 상태 변경을 처리하는 슬롯"""
        if item.column() == 0:  # 체크박스가 0번 열에 있는지 확인
            # 원본 모델의 행 인덱스 가져오기
            row = item.row()
            
            # 해당 행의 멤버 파일 경로 가져오기 (3번 열)
            member_item = self.duplicate_table_model.item(row, 3)
            if not member_item:
                print(f"[Checkbox] 경고: 행 {row}의 멤버 항목을 찾을 수 없습니다.")
                return
                
            member_path = member_item.text()
            
            # 체크 상태에 따라 선택된 항목 목록 업데이트
            if item.checkState() == Qt.Checked:
                # 테이블에 해당 경로가 실제로 존재하는지 확인
                exists_in_table = False
                for check_row in range(self.duplicate_table_model.rowCount()):
                    check_item = self.duplicate_table_model.item(check_row, 3)
                    if check_item and check_item.text() == member_path:
                        exists_in_table = True
                        break
                        
                if exists_in_table:
                    if member_path not in self.selected_items:
                        self.selected_items.append(member_path)
                        print(f"[Checkbox] 항목 선택됨: {member_path}")
                else:
                    print(f"[Checkbox] 경고: {member_path}가 테이블에 존재하지 않습니다.")
                    # 체크박스 상태 복원 (시그널 차단)
                    self.duplicate_table_model.blockSignals(True)
                    item.setCheckState(Qt.Unchecked)
                    self.duplicate_table_model.blockSignals(False)
            else:
                if member_path in self.selected_items:
                    self.selected_items.remove(member_path)
                    print(f"[Checkbox] 항목 선택 해제됨: {member_path}")
            
            # 현재 선택된 항목 수 표시
            self.status_label.setText(f"선택된 항목: {len(self.selected_items)}개")
            
            # 디버깅용 로그
            print(f"[Checkbox] 현재 선택된 항목 수: {len(self.selected_items)}")
            
            # 일괄 작업 버튼 활성화/비활성화
            self._update_batch_buttons_state()
    
    def _update_batch_buttons_state(self):
        """선택된 항목 수에 따라 일괄 작업 버튼 상태 업데이트"""
        has_selected_items = len(self.selected_items) > 0
        has_table_items = self.duplicate_table_model.rowCount() > 0
        
        # 선택 버튼은 테이블에 항목이 있을 때만 활성화
        self.select_all_button.setEnabled(has_table_items)
        self.select_none_button.setEnabled(has_selected_items and has_table_items)
        
        # 일괄 작업 버튼은 선택된 항목이 있을 때만 활성화
        self.batch_delete_button.setEnabled(has_selected_items)
        self.batch_move_button.setEnabled(has_selected_items)
        
        # 디버깅용 로그
        print(f"[Button State] 테이블 항목 수: {self.duplicate_table_model.rowCount()}, 선택된 항목 수: {len(self.selected_items)}")
        print(f"[Button State] 버튼 상태 - 전체선택: {self.select_all_button.isEnabled()}, 선택해제: {self.select_none_button.isEnabled()}, 삭제: {self.batch_delete_button.isEnabled()}, 이동: {self.batch_move_button.isEnabled()}")
    
    def select_all_items(self):
        """테이블의 모든 항목 선택"""
        # 먼저 선택 항목 목록 초기화
        self.selected_items.clear()
        
        # 모든 행을 순회하며 체크박스 체크
        for row in range(self.duplicate_table_model.rowCount()):
            # 체크박스 아이템 가져오기 (0번 열)
            checkbox_item = self.duplicate_table_model.item(row, 0)
            if checkbox_item:
                # 멤버 파일 경로 가져오기 (3번 열)
                member_item = self.duplicate_table_model.item(row, 3)
                if member_item:
                    member_path = member_item.text()
                    # 아이템이 존재하고 현재 선택되지 않았다면 선택 목록에 추가
                    if member_path not in self.selected_items:
                        self.selected_items.append(member_path)
                
                # itemChanged 시그널이 발생하지 않도록 블로킹
                self.duplicate_table_model.blockSignals(True)
                checkbox_item.setCheckState(Qt.Checked)
                self.duplicate_table_model.blockSignals(False)
        
        # 상태 라벨 업데이트
        self.status_label.setText(f"선택된 항목: {len(self.selected_items)}개")
        print(f"모든 항목 선택됨: {len(self.selected_items)}개")
        
        # 일괄 작업 버튼 활성화/비활성화
        self._update_batch_buttons_state()
    
    def clear_selection(self):
        """선택된 모든 항목 선택 해제"""
        # 선택 항목 목록 초기화
        self.selected_items.clear()
        
        # 모든 행을 순회하며 체크박스 해제
        for row in range(self.duplicate_table_model.rowCount()):
            # 체크박스 아이템 가져오기
            checkbox_item = self.duplicate_table_model.item(row, 0)
            if checkbox_item:
                # itemChanged 시그널이 발생하지 않도록 블로킹
                self.duplicate_table_model.blockSignals(True)
                checkbox_item.setCheckState(Qt.Unchecked)
                self.duplicate_table_model.blockSignals(False)
        
        # 상태 라벨 업데이트
        self.status_label.setText("선택된 항목: 0개")
        print("모든 선택 해제됨")
        
        # 일괄 작업 버튼 활성화/비활성화
        self._update_batch_buttons_state()
    
    def delete_selected_items(self):
        """선택된 모든 항목 삭제"""
        if not self.selected_items:
            QMessageBox.information(self, "알림", "선택된 항목이 없습니다.")
            return
        
        # 삭제 확인 메시지
        reply = QMessageBox.question(
            self, 
            "삭제 확인", 
            f"선택한 {len(self.selected_items)}개 항목을 삭제하시겠습니까?\n이 작업은 실행취소할 수 있습니다.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 전체 항목 갯수 저장 (모든 항목이 삭제되었는지 확인용)
        total_items_before = self.duplicate_table_model.rowCount()
        selected_count = len(self.selected_items)
        print(f"[Batch Delete] 전체 항목 수: {total_items_before}, 선택된 항목 수: {selected_count}")
        
        # 삭제할 항목들의 행 인덱스 수집 (나중에 UI 갱신에 사용)
        rows_to_remove = []
        selected_paths_copy = self.selected_items.copy()  # 복사본 사용
        
        # 선택된 항목들에 대한 정보 수집
        items_info = []
        for member_path in selected_paths_copy:
            # 멤버 파일이 속한 그룹 ID와 대표 파일 경로 찾기
            group_id = None
            representative_path = None
            
            # 테이블에서 해당 파일 정보 찾기
            for row in range(self.duplicate_table_model.rowCount()):
                member_item = self.duplicate_table_model.item(row, 3)
                if member_item and member_item.text() == member_path:
                    rep_item = self.duplicate_table_model.item(row, 2)
                    group_id_item = self.duplicate_table_model.item(row, 5)
                    
                    if rep_item and group_id_item:
                        representative_path = rep_item.text()
                        group_id = group_id_item.text()
                        rows_to_remove.append(row)  # 삭제할 행 인덱스 저장
                        break
            
            if group_id and representative_path:
                # 각 파일에 대한 필요한 정보를 actions 리스트에 추가
                items_info.append({
                    'deleted_path': member_path,
                    'group_id': group_id,
                    'representative_path': representative_path,
                    # Undo 작업을 위한 필요한 정보 추가
                    'member_paths': [path for path, _, _ in self.duplicate_groups_data.get(group_id, [])],
                    'snapshot_rep': self.group_representatives.get(group_id),
                    'snapshot_members': copy.deepcopy(self.duplicate_groups_data.get(group_id, []))
                })
            else:
                print(f"경고: {member_path} 파일의 그룹 정보를 찾을 수 없습니다.")
        
        # 배치 삭제 작업 수행 (UndoManager의 batch_delete_files 메서드 사용)
        success, deleted_files = self.undo_manager.batch_delete_files(items_info)
        
        if success and deleted_files:
            # 삭제된 파일들에 대한 그룹 데이터 업데이트
            for action in items_info:
                if action['deleted_path'] in deleted_files:
                    self._update_groups_after_deletion(
                        action['deleted_path'], 
                        action['group_id'], 
                        action['representative_path']
                    )
            
            # 테이블에서 선택된 행들을 직접 제거 (UI 즉시 갱신)
            print(f"[Batch Delete] 테이블에서 {len(rows_to_remove)}개 행을 직접 제거합니다.")
            for row in sorted(rows_to_remove, reverse=True):
                try:
                    self.duplicate_table_model.removeRow(row)
                except Exception as e:
                    print(f"[Batch Delete] 행 제거 중 오류: {e}")
            
            # 테이블 뷰 강제 갱신
            self.duplicate_table_view.reset()
            
            # 모든 항목 삭제 확인
            might_be_all_deleted = (selected_count >= total_items_before)
            current_row_count = self.duplicate_table_model.rowCount()
            print(f"[Batch Delete] 현재 행 수: {current_row_count}, 가능한 모든 항목 삭제 여부: {might_be_all_deleted}")
            
            # 모든 항목이 삭제된 것으로 보이면 테이블 모델 명시적 초기화
            if might_be_all_deleted or current_row_count == 0:
                print("[Batch Delete] 모든 항목이 삭제된 것으로 판단됩니다. 테이블 뷰 초기화를 강제합니다.")
                # 테이블 모델 업데이트 강제
                self.duplicate_table_view.reset()
                # 그룹 데이터 초기화 확인
                if len(self.duplicate_groups_data) == 0 and len(self.group_representatives) == 0:
                    print("[Batch Delete] 그룹 데이터가 비어있음을 확인했습니다.")
                else:
                    print(f"[Batch Delete] 경고: 그룹 데이터가 아직 남아있습니다. 그룹: {len(self.duplicate_groups_data)}, 대표: {len(self.group_representatives)}")
                    
                # 이미지 패널 초기화
                self.left_image_label.clear()
                self.left_info_label.setText("Image Area")
                self.right_image_label.clear()
                self.right_info_label.setText("Image Area")
            
            # UI 업데이트 (제거된 항목이 있는 경우에만)
            if len(rows_to_remove) > 0:
                print("[Batch Delete] UI 상태 업데이트를 실행합니다.")
                self._update_ui_after_action()
            
            # 선택 목록 초기화
            self.selected_items.clear()
            self._update_batch_buttons_state()
            
            # 상태 메시지 표시
            self.status_label.setText(f"{len(deleted_files)}개 항목 삭제 완료")
        else:
            QMessageBox.warning(self, "삭제 실패", "선택한 항목 중 삭제할 수 있는 항목이 없습니다.")
    
    def _update_groups_after_deletion(self, deleted_path, group_id, representative_path):
        """파일 삭제 후 그룹 데이터 업데이트"""
        # 내부 그룹 데이터에서 파일 제거
        if group_id in self.duplicate_groups_data:
            current_group_tuples = self.duplicate_groups_data[group_id]
            found_index = -1
            
            for i, (path, _, _) in enumerate(current_group_tuples):
                if path == deleted_path:
                    found_index = i
                    break
                    
            if found_index >= 0:
                del current_group_tuples[found_index]
                print(f"[Delete Update] 그룹 {group_id}에서 {os.path.basename(deleted_path)}를 제거했습니다. 남은 멤버: {len(current_group_tuples)}")
            
            # 대표 이미지 처리
            current_representative = self.group_representatives.get(group_id)
            if deleted_path == current_representative:
                if current_group_tuples:
                    new_representative_path, _, _ = current_group_tuples[0]
                    self.group_representatives[group_id] = new_representative_path
                    del current_group_tuples[0]
                    print(f"[Delete Update] 그룹 {group_id}: 새 대표 파일로 {os.path.basename(new_representative_path)}를 설정했습니다.")
                else:
                    print(f"[Delete Update] 그룹 {group_id}가 비었습니다. 그룹 데이터를 제거합니다.")
                    if group_id in self.duplicate_groups_data: 
                        del self.duplicate_groups_data[group_id]
                    if group_id in self.group_representatives: 
                        del self.group_representatives[group_id]
            else:
                # 대표가 아닌데 멤버 목록이 비게 되는 경우 (마지막 멤버가 삭제된 경우)
                if not current_group_tuples:
                    print(f"[Delete Update] 그룹 {group_id}에서 마지막 멤버가 삭제되었습니다. 그룹 데이터를 제거합니다.")
                    if group_id in self.duplicate_groups_data: 
                        del self.duplicate_groups_data[group_id]
                    if group_id in self.group_representatives: 
                        del self.group_representatives[group_id]
    
    def move_selected_items(self):
        """선택된 모든 항목 이동"""
        if not self.selected_items:
            QMessageBox.information(self, "알림", "선택된 항목이 없습니다.")
            return
        
        # 이동할 대상 폴더 선택
        target_dir = QFileDialog.getExistingDirectory(self, "선택한 파일을 이동할 폴더 선택")
        if not target_dir:
            return  # 사용자가 취소함
        
        # 전체 항목 갯수 저장 (모든 항목이 이동되었는지 확인용)
        total_items_before = self.duplicate_table_model.rowCount()
        selected_count = len(self.selected_items)
        print(f"[Batch Move] 전체 항목 수: {total_items_before}, 선택된 항목 수: {selected_count}")
        
        # 이동할 항목들의 행 인덱스 수집 (나중에 UI 갱신에 사용)
        rows_to_remove = []
        selected_paths_copy = self.selected_items.copy()  # 복사본 사용
        
        # 선택된 항목들에 대한 정보 수집
        items_info = []
        for member_path in selected_paths_copy:
            # 멤버 파일이 속한 그룹 ID와 대표 파일 경로 찾기
            group_id = None
            representative_path = None
            
            # 테이블에서 해당 파일 정보 찾기
            for row in range(self.duplicate_table_model.rowCount()):
                member_item = self.duplicate_table_model.item(row, 3)
                if member_item and member_item.text() == member_path:
                    rep_item = self.duplicate_table_model.item(row, 2)
                    group_id_item = self.duplicate_table_model.item(row, 5)
                    
                    if rep_item and group_id_item:
                        representative_path = rep_item.text()
                        group_id = group_id_item.text()
                        rows_to_remove.append(row)  # 이동할 행 인덱스 저장
                        break
            
            if group_id and representative_path:
                # 각 파일에 대한 필요한 정보를 actions 리스트에 추가
                items_info.append({
                    'moved_from': member_path,
                    'destination_folder': target_dir,
                    'group_id': group_id,
                    'representative_path': representative_path,
                    # Undo 작업을 위한 필요한 정보 추가
                    'member_paths': [path for path, _, _ in self.duplicate_groups_data.get(group_id, [])],
                    'snapshot_rep': self.group_representatives.get(group_id),
                    'snapshot_members': copy.deepcopy(self.duplicate_groups_data.get(group_id, []))
                })
            else:
                print(f"경고: {member_path} 파일의 그룹 정보를 찾을 수 없습니다.")
        
        # 배치 이동 작업 수행 (UndoManager의 batch_move_files 메서드 사용)
        success, moved_files = self.undo_manager.batch_move_files(items_info)
        
        if success and moved_files:
            # 이동된 파일들에 대한 그룹 데이터 업데이트
            for source_path, destination_path in moved_files:
                # 해당 원본 파일의 그룹 정보 찾기
                for action in items_info:
                    if action['moved_from'] == source_path:
                        self._update_groups_after_move(
                            source_path, 
                            destination_path, 
                            action['group_id']
                        )
                        break
            
            # 테이블에서 선택된 행들을 직접 제거 (UI 즉시 갱신)
            print(f"[Batch Move] 테이블에서 {len(rows_to_remove)}개 행을 직접 제거합니다.")
            for row in sorted(rows_to_remove, reverse=True):
                try:
                    self.duplicate_table_model.removeRow(row)
                except Exception as e:
                    print(f"[Batch Move] 행 제거 중 오류: {e}")
            
            # 테이블 뷰 강제 갱신
            self.duplicate_table_view.reset()
            
            # 모든 항목 이동 확인
            might_be_all_moved = (selected_count >= total_items_before)
            current_row_count = self.duplicate_table_model.rowCount()
            print(f"[Batch Move] 현재 행 수: {current_row_count}, 가능한 모든 항목 이동 여부: {might_be_all_moved}")
            
            # 모든 항목이 이동된 것으로 보이면 테이블 모델 명시적 초기화
            if might_be_all_moved or current_row_count == 0:
                print("[Batch Move] 모든 항목이 이동된 것으로 판단됩니다. 테이블 뷰 초기화를 강제합니다.")
                # 테이블 모델 업데이트 강제
                self.duplicate_table_view.reset()
                # 그룹 데이터 초기화 확인
                if len(self.duplicate_groups_data) == 0 and len(self.group_representatives) == 0:
                    print("[Batch Move] 그룹 데이터가 비어있음을 확인했습니다.")
                else:
                    print(f"[Batch Move] 경고: 그룹 데이터가 아직 남아있습니다. 그룹: {len(self.duplicate_groups_data)}, 대표: {len(self.group_representatives)}")
            
            # UI 업데이트 (제거된 항목이 있는 경우에만)
            if len(rows_to_remove) > 0:
                print("[Batch Move] UI 상태 업데이트를 실행합니다.")
                self._update_ui_after_action()
            
            # 선택 목록 초기화
            self.selected_items.clear()
            self._update_batch_buttons_state()
            
            # 상태 메시지 표시
            self.status_label.setText(f"{len(moved_files)}개 항목 이동 완료")
        else:
            QMessageBox.warning(self, "이동 실패", "선택한 항목 중 이동할 수 있는 항목이 없습니다.")
    
    def _update_groups_after_move(self, source_path, destination_path, group_id):
        """파일 이동 후 그룹 데이터 업데이트"""
        if group_id in self.duplicate_groups_data:
            # 내부 그룹 데이터 업데이트
            current_group_tuples = self.duplicate_groups_data[group_id]
            for i, (path, similarity, rank) in enumerate(current_group_tuples):
                if path == source_path:
                    current_group_tuples[i] = (destination_path, similarity, rank)
                    print(f"[Move Update] 그룹 데이터 업데이트됨: {os.path.basename(source_path)} -> {os.path.basename(destination_path)}")
                    break
            
            # 대표 이미지 처리
            if source_path == self.group_representatives.get(group_id):
                self.group_representatives[group_id] = destination_path
                print(f"[Move Update] 대표 파일 경로 업데이트됨: {os.path.basename(source_path)} -> {os.path.basename(destination_path)}")
                
            return True
        return False

if __name__ == '__main__':
    # DPI 스케일링 활성화 
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    
    setup_logging() # 로깅 설정
    app = QApplication(sys.argv) # QApplication 생성
    app.setStyle('Fusion') # 스타일 적용
    
    # 애플리케이션 아이콘 설정 (선택적, main.py 에서도 설정됨)
    # if os.path.exists(ICON_PATH): # ICON_PATH 는 여기서 정의되지 않았으므로 제거
    #     app.setWindowIcon(QIcon(ICON_PATH))
        
    window = MainWindow() # 메인 윈도우 생성
    window.show() # 윈도우 표시
    sys.exit(app.exec_()) # 이벤트 루프 시작 