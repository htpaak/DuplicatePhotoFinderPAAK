import os
import uuid
from PyQt5.QtGui import QStandardItem
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication # processEvents 용
from typing import TYPE_CHECKING, Dict, List, Tuple

# MainWindow 타입 힌트만 임포트 (순환 참조 방지)
if TYPE_CHECKING:
    from .main_window import MainWindow
    from image_processor import DuplicateGroupWithSimilarity # 입력 타입 힌트용

class ScanResultProcessor:
    """스캔 결과를 처리하고 MainWindow의 데이터와 UI를 업데이트하는 클래스"""
    def __init__(self, main_window: 'MainWindow'):
        self.main_window = main_window

    def process_results(self, total_files: int, processed_count: int, duplicate_groups_with_similarity: 'DuplicateGroupWithSimilarity'):
        """스캔 완료 시그널을 처리하여 결과를 테이블에 업데이트합니다."""
        mw = self.main_window # 편의상 짧은 변수명 사용

        # 스캔 완료 상태 업데이트
        mw.status_label.setText(f"Scan complete. Found {len(duplicate_groups_with_similarity)} duplicate groups in {processed_count}/{total_files} files.")

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
             mw.duplicate_table_model.appendRow([item_rank, item_representative, item_member, item_similarity, item_group_id])
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