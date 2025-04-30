from PyQt5.QtCore import QModelIndex, Qt, QSortFilterProxyModel

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