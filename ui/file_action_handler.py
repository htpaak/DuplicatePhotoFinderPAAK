import os
import copy
import traceback
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QLabel
from PyQt5.QtCore import QModelIndex
from typing import TYPE_CHECKING, Optional, Tuple

# 순환 참조 방지를 위해 MainWindow 타입 힌트만 임포트
if TYPE_CHECKING:
    from .main_window import MainWindow
    from .image_label import ImageLabel # _get_selected_item_data는 MainWindow에 남기거나 여기서도 필요

class FileActionHandler:
    """MainWindow의 파일 삭제 및 이동 액션을 처리하는 클래스"""
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window

    def delete_selected_image(self, target: str):
        """선택된 이미지를 휴지통으로 보내고 그룹 데이터를 업데이트합니다."""
        print(f"[Delete Entry] delete_selected_image called with target: {target}")
        # --- 액션 전 상태 저장 (프록시 인덱스 및 경로) ---
        try:
            print("[Delete Debug] Getting selected indexes...")
            selected_proxy_indexes = self.main_window.duplicate_table_view.selectedIndexes()
            print("[Delete Debug] Got selected indexes.")
            if not selected_proxy_indexes:
                print("[Delete Debug] No selection found.")
                QMessageBox.warning(self.main_window, "Warning", "Please select an image pair from the list.")
                return

            selected_proxy_index = selected_proxy_indexes[0]
            print(f"[Delete Debug] Got proxy index: row={selected_proxy_index.row()}, col={selected_proxy_index.column()}")
            source_index = self.main_window.duplicate_table_proxy_model.mapToSource(selected_proxy_index)
            print(f"[Delete Debug] Mapped to source index: row={source_index.row()}, col={source_index.column()}")
            selected_row = source_index.row() # 소스 모델 행 (데이터 접근용)
            self.main_window.previous_selection_index = selected_proxy_index.row() # *** 프록시 행 인덱스 저장 ***
            print(f"[Delete Debug] Stored previous proxy index: {self.main_window.previous_selection_index}")

            representative_item = self.main_window.duplicate_table_model.item(selected_row, 1)
            print("[Delete Debug] Got representative item.")
            member_item = self.main_window.duplicate_table_model.item(selected_row, 2)
            print("[Delete Debug] Got member item.")
            group_id_item = self.main_window.duplicate_table_model.item(selected_row, 4)
            print("[Delete Debug] Got group_id item.")

            if not (representative_item and member_item and group_id_item):
                print("[Delete Debug] Failed to get one or more items.")
                QMessageBox.warning(self.main_window, "Warning", "Could not get item data.")
                self.main_window.previous_selection_index = None # 저장 실패 시 초기화
                return

            # 액션 대상 경로와 그룹 ID 가져오기
            original_representative_path = representative_item.text()
            print(f"[Delete Debug] Got rep path: {original_representative_path}")
            original_member_path = member_item.text()
            print(f"[Delete Debug] Got mem path: {original_member_path}")
            group_id = group_id_item.text()
            print(f"[Delete Debug] Got group_id: {group_id}")
            self.main_window.last_acted_group_id = group_id # 복원 시 그룹 식별용
            self.main_window.last_acted_representative_path = original_representative_path
            self.main_window.last_acted_member_path = original_member_path
            print(f"[Delete Debug] Stored last acted paths and group.")

            target_label = self.main_window.left_image_label if target == 'original' else self.main_window.right_image_label
            image_path_to_delete = original_representative_path if target == 'original' else original_member_path
            print(f"[Delete Debug] Determined path to delete: {image_path_to_delete}")
            # --- 저장 끝 ---

            # --- 복원을 위한 그룹 데이터 스냅샷 저장 ---
            try:
                restore_snapshot_rep = self.main_window.group_representatives.get(group_id)
                # deepcopy 필요
                restore_snapshot_members = copy.deepcopy(self.main_window.duplicate_groups_data.get(group_id, []))
                print(f"[Delete Debug] Created restore snapshot for group {group_id}. Rep: {os.path.basename(restore_snapshot_rep) if restore_snapshot_rep else 'None'}, Members: {len(restore_snapshot_members)}")
            except Exception as snap_err:
                print(f"[Delete Error] Failed to create restore snapshot: {snap_err}")
                restore_snapshot_rep = None
                restore_snapshot_members = None
                QMessageBox.critical(self.main_window, "Error", "Failed to prepare for undo. Cannot proceed.")
                self.main_window.previous_selection_index = None
                self.main_window.last_acted_group_id = None
                return
            # --- 스냅샷 저장 끝 ---

            if group_id not in self.main_window.duplicate_groups_data or group_id not in self.main_window.group_representatives:
                print(f"[Delete Debug] Group data inconsistent for group_id: {group_id}")
                QMessageBox.critical(self.main_window, "Error", "Group data not found. Cannot process delete.")
                self.main_window.last_acted_group_id = None
                self.main_window.previous_selection_index = None
                return
            print("[Delete Debug] Group data consistency check passed.")

            # 실행 취소 정보 준비
            representative_path_for_undo = self.main_window.group_representatives[group_id]
            print("[Delete Debug] Got representative for undo.")
            member_paths_for_undo = [path for path, _, _ in self.main_window.duplicate_groups_data[group_id]]
            print("[Delete Debug] Got member paths for undo.")
            all_original_paths_for_undo = [representative_path_for_undo] + member_paths_for_undo
            print("[Delete Debug] Prepared all paths for undo.")

            # 1. 파일 삭제 시도 (UndoManager 사용)
            print("[Delete Debug] Attempting to delete file via UndoManager...")
            # undo_manager 는 main_window 를 통해 접근
            if self.main_window.undo_manager.delete_file(image_path_to_delete, group_id, representative_path_for_undo, all_original_paths_for_undo, restore_snapshot_rep, restore_snapshot_members):
                print(f"[Delete Debug] File sent to trash (via UndoManager): {image_path_to_delete}")

                # 2. 내부 그룹 데이터에서 파일 제거
                print("[Delete Debug] Removing file from internal group data...")
                current_group_tuples = self.main_window.duplicate_groups_data[group_id]
                print(f"[Delete Debug] current_group_tuples before removal (len={len(current_group_tuples)}): {[(os.path.basename(p), s, sq) for p, s, sq in current_group_tuples[:5]]}...")
                found_and_removed = False
                for i, (path, _, _) in enumerate(current_group_tuples):
                    if path == image_path_to_delete:
                        print(f"[Delete Debug] Found item to remove at index {i}")
                        del current_group_tuples[i]
                        found_and_removed = True
                        print(f"[Delete Debug] Removed {os.path.basename(image_path_to_delete)} from group {group_id}. Remaining members: {len(current_group_tuples)}")
                        break
                if not found_and_removed:
                     print(f"[Delete Debug] Warning: {image_path_to_delete} not found in group data {group_id} upon delete.")
                print("[Delete Debug] Finished removing from internal group data.")

                # 3. 대표 이미지 처리
                print("[Delete Debug] Checking if representative needs update...")
                current_representative = self.main_window.group_representatives.get(group_id)
                if image_path_to_delete == current_representative:
                    print("[Delete Debug] Deleted item was the representative.")
                    if current_group_tuples:
                        print("[Delete Debug] Setting new representative...")
                        new_representative_path, _, _ = current_group_tuples[0]
                        self.main_window.group_representatives[group_id] = new_representative_path
                        del current_group_tuples[0]
                        print(f"[Delete Debug] Group {group_id}: New representative set to {os.path.basename(new_representative_path)}")
                        if not current_group_tuples:
                             print("[Delete Debug] Group became empty after setting new representative.")
                    else:
                        print(f"[Delete Debug] Group {group_id} is now empty after deleting the only representative, removing group data.")
                        if group_id in self.main_window.duplicate_groups_data: del self.main_window.duplicate_groups_data[group_id]
                        if group_id in self.main_window.group_representatives: del self.main_window.group_representatives[group_id]
                        print("[Delete Debug] Group data removed.")
                else:
                    print("[Delete Debug] Deleted item was not the representative.")
                    # 대표가 아닌데 멤버 목록이 비게 되는 경우 (마지막 멤버가 삭제된 경우)
                    if not current_group_tuples:
                        print(f"[Delete Debug] Last member deleted from group {group_id}. Removing group data.")
                        if group_id in self.main_window.duplicate_groups_data: del self.main_window.duplicate_groups_data[group_id]
                        if group_id in self.main_window.group_representatives: del self.main_window.group_representatives[group_id]
                        print("[Delete Debug] Group data removed.")


                # 4 & 5. 테이블 업데이트 (MainWindow의 메서드 호출)
                if group_id in self.main_window.duplicate_groups_data and self.main_window.duplicate_groups_data[group_id]:
                     print(f"[Delete Debug] Calling _update_table_for_group for group {group_id}...")
                     self.main_window._update_table_for_group(group_id) # MainWindow 메서드 호출
                     print(f"[Delete Debug] Finished _update_table_for_group for group {group_id}.")
                elif group_id not in self.main_window.duplicate_groups_data or not self.main_window.duplicate_groups_data.get(group_id):
                     print(f"[Delete Debug] Group {group_id} removed or empty, removing rows from table model...")
                     rows_to_remove = []
                     for row in range(self.main_window.duplicate_table_model.rowCount()):
                          item = self.main_window.duplicate_table_model.item(row, 4) # Group ID
                          if item and item.text() == group_id:
                               print(f"[Delete Debug] Found row {row} to remove for group {group_id}")
                               rows_to_remove.append(row)
                     if rows_to_remove:
                         print(f"[Delete Debug] Removing rows: {rows_to_remove}")
                         for row in sorted(rows_to_remove, reverse=True):
                              self.main_window.duplicate_table_model.removeRow(row)
                         print("[Delete Debug] Rows removed from table model.")
                     else:
                         print("[Delete Debug] No rows found to remove for the deleted/empty group.")

                # 6. UI 상태 업데이트 (MainWindow의 메서드 호출)
                print("[Delete Debug] Calling _update_ui_after_action...")
                self.main_window._update_ui_after_action() # MainWindow 메서드 호출
                print("[Delete Debug] Delete action finished successfully.")
        except Exception as e:
            print(f"[Delete Error] Unhandled exception in delete setup: {e}")
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Critical Error", f"An unexpected error occurred during delete setup: {e}")
            self.main_window.previous_selection_index = None
            self.main_window.last_acted_group_id = None
            self.main_window.last_acted_representative_path = None
            self.main_window.last_acted_member_path = None

    def move_selected_image(self, target: str):
        """선택된 이미지를 이동하고 그룹 데이터를 업데이트합니다."""
        print(f"[Move Entry] move_selected_image called with target: {target}")
        # --- 액션 전 상태 저장 (프록시 인덱스 및 경로) ---
        selected_proxy_indexes = self.main_window.duplicate_table_view.selectedIndexes()
        if not selected_proxy_indexes:
            QMessageBox.warning(self.main_window, "Warning", "Please select an image pair from the list.")
            return

        selected_proxy_index = selected_proxy_indexes[0]
        source_index = self.main_window.duplicate_table_proxy_model.mapToSource(selected_proxy_index)
        selected_row = source_index.row() # 소스 모델 행
        self.main_window.previous_selection_index = selected_proxy_index.row() # *** 프록시 행 인덱스 저장 ***

        representative_item = self.main_window.duplicate_table_model.item(selected_row, 1)
        member_item = self.main_window.duplicate_table_model.item(selected_row, 2)
        group_id_item = self.main_window.duplicate_table_model.item(selected_row, 4)

        if not (representative_item and member_item and group_id_item):
            QMessageBox.warning(self.main_window, "Warning", "Could not get item data.")
            self.main_window.previous_selection_index = None
            return

        original_representative_path = representative_item.text()
        original_member_path = member_item.text()
        group_id = group_id_item.text()
        self.main_window.last_acted_group_id = group_id
        self.main_window.last_acted_representative_path = original_representative_path
        self.main_window.last_acted_member_path = original_member_path

        image_path_to_move = original_representative_path if target == 'original' else original_member_path
        print(f"[Move Debug] Determined path to move: {image_path_to_move}")

        if not os.path.exists(image_path_to_move):
            QMessageBox.critical(self.main_window, "Error", f"File to move does not exist:\n{image_path_to_move}")
            self.main_window.previous_selection_index = None
            self.main_window.last_acted_group_id = None
            return

        # 1. 대상 폴더 선택
        destination_folder = QFileDialog.getExistingDirectory(self.main_window, f"Select Destination Folder for {os.path.basename(image_path_to_move)}")
        if not destination_folder:
            print("[Move Debug] Folder selection cancelled.")
            self.main_window.previous_selection_index = None # 사용자가 취소 시 상태 초기화
            self.main_window.last_acted_group_id = None
            return

        print(f"[Move Debug] Destination folder selected: {destination_folder}")

        # 2. 실행 취소를 위한 데이터 준비
        try:
            snapshot_rep = self.main_window.group_representatives.get(group_id)
            # deepcopy 필요
            snapshot_members = copy.deepcopy(self.main_window.duplicate_groups_data.get(group_id, []))
            print(f"[Move Debug] Created restore snapshot for group {group_id}. Rep: {os.path.basename(snapshot_rep) if snapshot_rep else 'None'}, Members: {len(snapshot_members)}")

            representative_path_for_undo = snapshot_rep
            member_paths_for_undo = [path for path, _, _ in snapshot_members]
            all_original_paths_for_undo = [representative_path_for_undo] + member_paths_for_undo if representative_path_for_undo else member_paths_for_undo # 대표 없을 경우 대비
            print(f"[Move Debug] Prepared paths for undo: Rep={os.path.basename(representative_path_for_undo) if representative_path_for_undo else 'None'}, All={len(all_original_paths_for_undo)}")

            # undo_manager 는 main_window 를 통해 접근
            if self.main_window.undo_manager.move_file(image_path_to_move, destination_folder, group_id, representative_path_for_undo, all_original_paths_for_undo, snapshot_rep, snapshot_members):
                print(f"[Move Debug] File moved successfully (via UndoManager): {image_path_to_move} -> {destination_folder}")

                # 4. 내부 데이터 업데이트
                print("[Move Debug] Removing moved file from internal group data...")
                current_group_tuples = self.main_window.duplicate_groups_data.get(group_id)
                if current_group_tuples is None:
                    print(f"[Move Warning] Group data for {group_id} already missing after move?")
                    self.main_window._update_ui_after_action() # UI 정리 시도
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
                current_representative = self.main_window.group_representatives.get(group_id)
                if image_path_to_move == current_representative:
                    print("[Move Debug] Moved item was the representative.")
                    if current_group_tuples:
                        print("[Move Debug] Setting new representative...")
                        new_representative_path, _, _ = current_group_tuples[0]
                        self.main_window.group_representatives[group_id] = new_representative_path
                        del current_group_tuples[0] # 새 대표는 멤버 목록에서 제거
                        print(f"[Move Debug] Group {group_id}: New representative set to {os.path.basename(new_representative_path)}")
                        if not current_group_tuples:
                             print("[Move Debug] Group became empty after setting new representative.")
                             # 그룹 제거는 아래 로직에서 처리
                    else:
                        print(f"[Move Debug] Group {group_id} is now empty after moving the only representative, removing group data.")
                        if group_id in self.main_window.duplicate_groups_data: del self.main_window.duplicate_groups_data[group_id]
                        if group_id in self.main_window.group_representatives: del self.main_window.group_representatives[group_id]
                        print("[Move Debug] Group data removed.")
                else:
                    print("[Move Debug] Moved item was not the representative.")
                    if not current_group_tuples:
                        # 대표가 아닌 마지막 멤버가 이동된 경우
                        print(f"[Move Debug] Last member moved from group {group_id}. Removing group data.")
                        if group_id in self.main_window.duplicate_groups_data: del self.main_window.duplicate_groups_data[group_id]
                        if group_id in self.main_window.group_representatives: del self.main_window.group_representatives[group_id]
                        print("[Move Debug] Group data removed.")

                # 6. 테이블 및 UI 업데이트 (MainWindow의 메서드 호출)
                if group_id in self.main_window.duplicate_groups_data and self.main_window.duplicate_groups_data[group_id]:
                     print(f"[Move Debug] Calling _update_table_for_group for group {group_id}...")
                     self.main_window._update_table_for_group(group_id) # MainWindow 메서드 호출
                     print(f"[Move Debug] Finished _update_table_for_group for group {group_id}.")
                elif group_id not in self.main_window.duplicate_groups_data or not self.main_window.duplicate_groups_data.get(group_id):
                     print(f"[Move Debug] Group {group_id} removed or empty, removing rows from table model...")
                     rows_to_remove = []
                     for row in range(self.main_window.duplicate_table_model.rowCount()):
                          item = self.main_window.duplicate_table_model.item(row, 4) # Group ID
                          if item and item.text() == group_id:
                               print(f"[Move Debug] Found row {row} to remove for group {group_id}")
                               rows_to_remove.append(row)
                     if rows_to_remove:
                         print(f"[Move Debug] Removing rows: {rows_to_remove}")
                         for row in sorted(rows_to_remove, reverse=True):
                              self.main_window.duplicate_table_model.removeRow(row)
                         print("[Move Debug] Rows removed from table model.")
                     else:
                         print("[Move Debug] No rows found to remove for the deleted/empty group.")

                print("[Move Debug] Calling _update_ui_after_action...")
                self.main_window._update_ui_after_action() # MainWindow 메서드 호출
                print("[Move Debug] Move action finished successfully.")
            else:
                print(f"[Move Error] UndoManager reported failure moving {image_path_to_move}")
                self.main_window.previous_selection_index = None
                self.main_window.last_acted_group_id = None

        except Exception as e:
            print(f"[Move Error] Failed to move file {image_path_to_move}. Error: {e}")
            traceback.print_exc()
            QMessageBox.critical(self.main_window, "Move Error", f"Failed to move file:\n{os.path.basename(image_path_to_move)}\nError: {e}")
            self.main_window.previous_selection_index = None
            self.main_window.last_acted_group_id = None

