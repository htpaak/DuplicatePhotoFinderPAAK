from PyQt5.QtCore import QModelIndex, Qt, QSortFilterProxyModel

class SimilaritySortProxyModel(QSortFilterProxyModel):
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # --- 'Rank' 열 (인덱스 1) 또는 'Similarity' 열 (인덱스 4) 정렬 처리 --- 
        column = left.column()
        if column == 1: # 'Rank' 열
            left_rank_index = self.sourceModel().index(self.mapToSource(left).row(), 1)
            right_rank_index = self.sourceModel().index(self.mapToSource(right).row(), 1)
            left_data = self.sourceModel().data(left_rank_index, Qt.UserRole + 6) # Rank 데이터는 Role +6
            right_data = self.sourceModel().data(right_rank_index, Qt.UserRole + 6)
            # 'Rank' 열은 오름차순 (작은 번호 먼저)
            sort_order_multiplier = 1 
        elif column == 4: # 'Similarity' 열
            left_sim_index = self.sourceModel().index(self.mapToSource(left).row(), 4)
            right_sim_index = self.sourceModel().index(self.mapToSource(right).row(), 4)
            left_data = self.sourceModel().data(left_sim_index, Qt.UserRole + 4)
            right_data = self.sourceModel().data(right_sim_index, Qt.UserRole + 4)
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
            
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """체크박스 열(첫 번째 열)은 체크 가능하게 설정하고 나머지 열은 읽기 전용으로 설정"""
        if not index.isValid():
            return Qt.NoItemFlags
            
        # 기본 플래그 가져오기
        flags = super().flags(index)
        
        # 체크박스 열(인덱스 0)은 체크 가능하게 설정
        if index.column() == 0:
            return flags | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        
        return flags
        
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """체크박스 열의 체크 상태를 처리"""
        if not index.isValid():
            return None
            
        # 체크박스 열(인덱스 0)의 체크 상태 처리
        if index.column() == 0:
            if role == Qt.CheckStateRole:
                return self.sourceModel().data(self.mapToSource(index), Qt.CheckStateRole)
        
        return super().data(index, role)
        
    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        """체크박스 상태 변경 처리"""
        if not index.isValid():
            return False
            
        # 체크박스 열(인덱스 0)의 체크 상태 변경 처리
        if index.column() == 0 and role == Qt.CheckStateRole:
            return self.sourceModel().setData(self.mapToSource(index), value, role)
            
        return super().setData(index, value, role) 