import os
import uuid
from PyQt5.QtGui import QStandardItem
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication # processEvents 용
from typing import TYPE_CHECKING, Dict, List, Tuple
# 파일 형식 정의 모듈 임포트
from supported_formats import VIDEO_ANIMATION_EXTENSIONS, VIDEO_ONLY_EXTENSIONS, FRAME_CHECK_FORMATS

# MainWindow 타입 힌트만 임포트 (순환 참조 방지)
if TYPE_CHECKING:
    from .main_window import MainWindow
    from image_processor import DuplicateGroupWithSimilarity # 입력 타입 힌트용

class ScanResultProcessor:
    """스캔 결과를 처리하고 MainWindow의 데이터와 UI를 업데이트하는 클래스"""
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window
        
    def is_video_file(self, file_path):
        """파일이 비디오/애니메이션 형식인지 확인합니다.
        이 함수는 파일 확장자만 확인하며, 실제 내용 검사는 하지 않습니다."""
        _, ext = os.path.splitext(file_path.lower())
        return ext in VIDEO_ONLY_EXTENSIONS or ext in FRAME_CHECK_FORMATS

    def process_results(self, total_files: int, processed_count: int, duplicate_groups_with_similarity: 'DuplicateGroupWithSimilarity'):
        """스캔 완료 시그널을 처리하여 결과를 테이블에 업데이트합니다."""
        mw = self.main_window # 편의상 짧은 변수명 사용

        # 스캔 완료 상태 업데이트
        include_subfolder_msg = " (including subfolders)" if mw.include_subfolders_checkbox.isChecked() else ""
        mw.status_label.setText(f"Scan complete{include_subfolder_msg}. Found {len(duplicate_groups_with_similarity)} duplicate groups in {processed_count}/{total_files} files.")

        # 내부 데이터 초기화
        mw.duplicate_groups_data.clear()
        mw.group_representatives.clear()
        mw.duplicate_table_model.removeRows(0, mw.duplicate_table_model.rowCount())

        # --- 유사도 기반 Rank 계산 로직 --- 
        all_duplicate_pairs = []
        temp_group_data = {}
        # 1. 모든 중복 쌍과 유사도(%) 수집
        for representative_path, members_with_similarity in duplicate_groups_with_similarity:
            if not members_with_similarity: continue
            group_id = str(uuid.uuid4()) # 임시 ID 부여 (나중에 테이블 채울 때 사용)
            temp_group_data[group_id] = {'rep': representative_path, 'members': []}
            
            # 파일 타입 확인 (비디오 또는 이미지)
            is_video = self.is_video_file(representative_path)
            
            for member_path, similarity in members_with_similarity:
                # 처리 방식을 파일 유형에 따라 분리
                if is_video:
                    # 비디오 파일은 이미 0-100 범위의 유사도 값을 갖고 있음
                    percentage_similarity = float(similarity)
                    print(f"비디오 유사도 처리: {os.path.basename(member_path)} -> {percentage_similarity:.1f}%")
                else:
                    # 이미지 파일은 해시 거리를 백분율로 변환
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
        mw.group_representatives.clear()
        mw.duplicate_groups_data.clear()
        for group_id, data in temp_group_data.items():
             mw.group_representatives[group_id] = data['rep']
             # 최종 저장 형식: (path, percentage_similarity, rank)
             mw.duplicate_groups_data[group_id] = [(m['path'], m['percentage'], m['rank']) for m in data['members']]
        # --- Rank 계산 로직 끝 --- 

        # --- 테이블 채우기 로직 (Rank 기반) ---
        # 정렬된 Rank 순서대로 테이블에 추가 (all_duplicate_pairs 사용)
        for rep_path, mem_path, percent_sim, group_id, original_sim in all_duplicate_pairs:
             rank = -1
             # 해당 멤버의 Rank 찾기 (이미 계산됨)
             for m_path, percent_sim_stored, r in mw.duplicate_groups_data.get(group_id, []):
                  if m_path == mem_path:
                       rank = r
                       break
             if rank == -1: continue # 오류 방지

             # 체크박스 아이템 생성
             item_checkbox = QStandardItem()
             item_checkbox.setCheckable(True)
             item_checkbox.setCheckState(Qt.Unchecked)
             print(f"[TableDebug] Created checkbox item for row {rank}, member={os.path.basename(mem_path)}")
             
             # Rank 열 아이템 생성
             item_rank = QStandardItem(str(rank))
             item_rank.setTextAlignment(Qt.AlignCenter)
             item_rank.setData(rank, Qt.UserRole + 6) # Rank 정렬용 데이터 (Role +6)
             item_rank.setFlags(item_rank.flags() & ~Qt.ItemIsEditable)
             
             item_representative = QStandardItem(rep_path)
             item_member = QStandardItem(mem_path)
             
             # 파일 타입에 따라 유사도 표시 형식 변경
             is_video = self.is_video_file(rep_path)
             
             if is_video:
                 # 비디오 파일의 경우 소수점 한 자리까지 표시
                 similarity_text = f"{percent_sim:.1f}%"
             else:
                 # 이미지 파일은 정수로 표시
                 similarity_text = f"{int(percent_sim)}%"
                 
             item_similarity = QStandardItem(similarity_text)
             item_similarity.setData(percent_sim, Qt.UserRole + 4)
             item_similarity.setTextAlignment(Qt.AlignCenter)
             item_group_id = QStandardItem(group_id)
             
             item_representative.setFlags(item_representative.flags() & ~Qt.ItemIsEditable)
             item_member.setFlags(item_member.flags() & ~Qt.ItemIsEditable)
             item_similarity.setFlags(item_similarity.flags() & ~Qt.ItemIsEditable)
             item_group_id.setFlags(item_group_id.flags() & ~Qt.ItemIsEditable)
             
             # 체크박스 아이템을 맨 앞에 추가
             row_items = [item_checkbox, item_rank, item_representative, item_member, item_similarity, item_group_id]
             print(f"[TableDebug] Adding row with {len(row_items)} items: {row_items[0]}, {row_items[1]}, ...")
             mw.duplicate_table_model.appendRow(row_items)
             print(f"[TableDebug] Row added to table model. Current row count: {mw.duplicate_table_model.rowCount()}")
        # --- 테이블 채우기 로직 수정 끝 ---

        if mw.duplicate_table_model.rowCount() > 0:
            # 초기 정렬이 Rank 기준이므로 첫 행 선택
            mw.duplicate_table_view.selectRow(0)
            # 첫 행 클릭 이벤트 발생 (MainWindow 메서드 호출)
            mw.on_table_item_clicked(mw.duplicate_table_proxy_model.index(0, 0)) 
        else:
            mw.left_image_label.clear()
            mw.left_info_label.setText("Image Info")
            mw.right_image_label.clear()
            mw.right_info_label.setText("Image Info") 