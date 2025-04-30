import sys
import os

# 프로젝트 루트 경로를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import shutil # shutil 임포트
import copy # copy 임포트 추가 (delete/move 메서드 내 import 제거 위함)
import traceback # traceback 임포트 추가
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
from typing import Optional, Dict, Any, List, Tuple # Tuple 임포트 추가
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
            # 스레드 및 워커 생성
            self.scan_thread = QThread()
            self.scan_worker = ScanWorker(folder_path)
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
        self.status_label.setText(f"Scanning... 0 / {self.total_files_to_scan}")
        QApplication.processEvents() # 메시지 즉시 업데이트

    def update_scan_progress(self, processed_count: int):
        """스캔 진행률 업데이트 슬롯"""
        if self.total_files_to_scan > 0:
            # "processed" 명시
            self.status_label.setText(f"Scanning... {processed_count} / {self.total_files_to_scan} files processed")
        else:
            self.status_label.setText(f"Scanning... Files processed: {processed_count}")

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
        # --- previous_selection_index 를 프록시 모델 기준으로 저장하도록 수정하겠습니다.
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
            self.duplicate_groups_data[group_id] = restore_snapshot_members
            self._update_table_for_group(group_id)
            current_sort_column = self.duplicate_table_view.horizontalHeader().sortIndicatorSection()
            current_sort_order = self.duplicate_table_view.horizontalHeader().sortIndicatorOrder()
            self.duplicate_table_proxy_model.sort(current_sort_column, current_sort_order)
            target_rep_path = self.last_acted_representative_path
            target_mem_path = self.last_acted_member_path
            restored_proxy_row_index = -1
            if target_rep_path and target_mem_path:
                for proxy_row in range(self.duplicate_table_proxy_model.rowCount()):
                     proxy_index_rep = self.duplicate_table_proxy_model.index(proxy_row, 1)
                     source_index_rep = self.duplicate_table_proxy_model.mapToSource(proxy_index_rep)
                     proxy_index_mem = self.duplicate_table_proxy_model.index(proxy_row, 2)
                     source_index_mem = self.duplicate_table_proxy_model.mapToSource(proxy_index_mem)
                     current_rep_item = self.duplicate_table_model.item(source_index_rep.row(), 1)
                     current_mem_item = self.duplicate_table_model.item(source_index_mem.row(), 2)
                     current_rep_path = current_rep_item.text() if current_rep_item else None
                     current_mem_path = current_mem_item.text() if current_mem_item else None
                     if current_rep_path == target_rep_path and current_mem_path == target_mem_path:
                          restored_proxy_row_index = proxy_row
                          break
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
    # if os.path.exists(ICON_PATH): # ICON_PATH 는 여기서 정의되지 않았으므로 제거
    #     app.setWindowIcon(QIcon(ICON_PATH))
        
    window = MainWindow() # 메인 윈도우 생성
    window.show() # 윈도우 표시
    sys.exit(app.exec_()) # 이벤트 루프 시작 