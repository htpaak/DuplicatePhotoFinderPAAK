import os
import numpy as np
import platform
import ctypes
from video_processor import VideoProcessor
# 파일 형식 정의 모듈 임포트
from supported_formats import VIDEO_ANIMATION_EXTENSIONS, VIDEO_SIMILARITY_THRESHOLD, FRAME_CHECK_FORMATS, VIDEO_ONLY_EXTENSIONS

class VideoDuplicateFinder:
    """비디오 중복을 찾기 위한 클래스"""
    
    def __init__(self, frame_positions=None, similarity_threshold=None, output_size=(16, 16)):
        """
        비디오 중복 찾기 엔진을 초기화합니다.
        
        매개변수:
            frame_positions: 비디오의 위치 백분율 목록 (기본값은 5개 지점)
            similarity_threshold: 중복으로 간주할 유사도 임계값 (기본값 85%)
            output_size: 추출할 프레임의 크기 (기본값 16x16)
        """
        self.video_processor = VideoProcessor()
        self.frame_positions = frame_positions or [10, 30, 50, 70, 90]  # 비디오 길이의 퍼센트 위치
        # 애니메이션 파일에 대해 더 엄격한 임계값 적용 (기본값 92%)
        self.similarity_threshold = similarity_threshold or 92.0  # 기본값 상향 조정
        self.output_size = output_size
        self.cache = {}  # 파일 경로 -> 시그니처 캐시
        self.current_os = platform.system()
        
    def is_video_file(self, file_path):
        """파일이 지원되는 비디오 형식인지 확인합니다"""
        if not os.path.isfile(file_path):
            return False
            
        # 모듈에서 정의된 비디오 및 애니메이션 확장자 사용
        _, ext = os.path.splitext(file_path.lower())
        
        # 항상 비디오로 처리할 확장자이거나 프레임 검사 필요 포맷인 경우
        return ext in VIDEO_ONLY_EXTENSIONS or ext in FRAME_CHECK_FORMATS
        
    def get_file_id(self, file_path):
        """파일의 고유 ID를 가져옵니다 (하드링크 감지용)"""
        try:
            if self.current_os == 'Windows':
                # Windows에서 파일 ID 가져오기
                file_id = os.stat(file_path).st_ino
                if file_id == 0:  # Windows에서 st_ino가 0인 경우가 많아 추가 확인
                    file_handle = ctypes.windll.kernel32.CreateFileW(
                        file_path, 0, 0, None, 3, 0, None
                    )
                    if file_handle != -1:
                        file_info = ctypes.create_string_buffer(32)
                        result = ctypes.windll.kernel32.GetFileInformationByHandle(
                            file_handle, file_info
                        )
                        ctypes.windll.kernel32.CloseHandle(file_handle)
                        if result:
                            # 볼륨 일련번호와 파일 인덱스 조합으로 ID 생성
                            vol_sn = int.from_bytes(file_info[0:4], byteorder='little')
                            index_high = int.from_bytes(file_info[8:12], byteorder='little')
                            index_low = int.from_bytes(file_info[12:16], byteorder='little')
                            return f"{vol_sn}:{index_high}{index_low}"
                return file_id
            else:
                # Unix 계열에서는 inode와 장치 ID 조합
                stat_info = os.stat(file_path)
                return f"{stat_info.st_dev}:{stat_info.st_ino}"
        except Exception as e:
            print(f"파일 ID 가져오기 오류: {e}")
            return None
            
    def is_same_file(self, path1, path2):
        """두 경로가 동일한 파일(하드링크)인지 확인합니다"""
        if path1 == path2:
            return True
            
        # 파일 실제 경로 비교 (심볼릭 링크 해결)
        try:
            real_path1 = os.path.realpath(path1)
            real_path2 = os.path.realpath(path2)
            if real_path1 == real_path2:
                return True
        except Exception:
            pass
            
        # 파일 ID로 비교 (하드링크)
        id1 = self.get_file_id(path1)
        id2 = self.get_file_id(path2)
        
        if id1 and id2 and id1 == id2:
            print(f"하드링크 감지: {os.path.basename(path1)} <-> {os.path.basename(path2)}")
            return True
            
        return False
        
    def get_video_signature(self, video_path):
        """
        비디오 파일의 시그니처(대표 프레임의 배열)를 생성합니다.
        캐싱을 통해 이미 처리된 비디오는 다시 처리하지 않습니다.
        """
        # 캐시에 있으면 캐시된 시그니처 반환
        if video_path in self.cache:
            return self.cache[video_path]
            
        if not self.is_video_file(video_path):
            return None
            
        # 여러 위치에서 프레임 추출
        frames = self.video_processor.extract_multiple_frames(
            video_path, 
            self.frame_positions,
            self.output_size
        )
        
        # 추출된 프레임이 없거나 너무 적으면 처리하지 않음
        if not frames or len(frames) < 3:  # 최소 3개 이상의 프레임 필요
            print(f"프레임이 충분하지 않습니다: {os.path.basename(video_path)}")
            return None
            
        # 너무 어두운 프레임 개수 확인
        dark_frames = sum(1 for frame in frames if self.video_processor.is_frame_too_dark(frame))
        if dark_frames > len(frames) / 2:  # 절반 이상의 프레임이 어두우면 처리하지 않음
            print(f"비디오가 너무 어둡습니다: {os.path.basename(video_path)}")
            return None
            
        # 시그니처 캐싱
        self.cache[video_path] = frames
        return frames
        
    def compare_signatures(self, sig1, sig2, path1=None, path2=None):
        """두 비디오 시그니처의 유사도를 비교합니다 (0-100% 범위)"""
        # 같은 파일명일 경우 100% 유사도 반환하는 코드 제거 (실제 비교로 대체)
        if not sig1 or not sig2:
            return 0
            
        # 프레임 수가 다르면 가능한 프레임끼리만 비교
        min_frames = min(len(sig1), len(sig2))
        if min_frames == 0:
            return 0
            
        similarities = []
        for i in range(min_frames):
            similarity = self.video_processor.calculate_frame_similarity(sig1[i], sig2[i])
            similarities.append(similarity)
            
        # 전체 프레임의 평균 유사도 반환
        avg_similarity = sum(similarities) / len(similarities)
        
        # 파일 크기가 거의 같은 경우와 애니메이션 파일에 대한 예외 처리 제거
        # 실제 프레임 비교 결과만 사용
        
        return avg_similarity
        
    def compare_with_flipped(self, sig1, sig2, path1=None, path2=None):
        """두 비디오 시그니처를 비교하고, 필요시 수평 반전하여 비교합니다"""
        # 정상 비교
        normal_similarity = self.compare_signatures(sig1, sig2, path1, path2)
        
        # 수평 반전 비교
        flipped_sig1 = self.video_processor.create_flipped_frames(sig1)
        flipped_similarity = self.compare_signatures(flipped_sig1, sig2, path1, path2)
        
        # 더 높은 유사도 선택
        if flipped_similarity > normal_similarity:
            print(f"수평 반전 비교가 더 높은 유사도를 보임: {os.path.basename(path1 or '')} vs {os.path.basename(path2 or '')}")
            return flipped_similarity, True
        
        return normal_similarity, False
        
    def find_duplicates(self, video_paths):
        """
        여러 비디오 파일 중 중복된 파일을 찾아 그룹화합니다.
        
        반환값:
            중복 그룹 목록. 각 그룹은 (대표 파일 경로, [(중복 파일 경로, 유사도)])로 구성됩니다.
        """
        # 비디오 시그니처 생성
        signatures = {}
        for path in video_paths:
            if self.is_video_file(path):
                sig = self.get_video_signature(path)
                if sig is not None:
                    signatures[path] = sig
                    print(f"비디오 시그니처 생성 완료: {os.path.basename(path)}")
        
        # 중복 그룹 생성
        duplicate_groups = []
        processed_files = set()
        
        # 모든 비디오 쌍을 비교하여 중복 찾기
        for i, (path1, sig1) in enumerate(signatures.items()):
            if path1 in processed_files:
                continue
                
            # 현재 파일이 다른 파일과 중복인지 확인
            duplicates = []
            
            for path2, sig2 in list(signatures.items())[i+1:]:
                if path2 in processed_files:
                    continue
                    
                # 하드링크인 경우 100% 유사도로 중복 처리
                if self.is_same_file(path1, path2):
                    duplicates.append((path2, 100.0))
                    processed_files.add(path2)
                    continue
                    
                # 유사도 계산 (수평 반전 포함)
                similarity, is_flipped = self.compare_with_flipped(sig1, sig2, path1, path2)
                print(f"비디오 유사도: {os.path.basename(path1)} vs {os.path.basename(path2)} = {similarity:.1f}%{' (반전됨)' if is_flipped else ''}")
                
                # 임계값 이상이면 중복으로 간주
                if similarity >= self.similarity_threshold:
                    duplicates.append((path2, similarity))
                    processed_files.add(path2)
                # 파일명만 같다고 유사하다고 판단하지 않음 - 이 코드 제거
            
            # 중복이 있으면 그룹 생성
            if duplicates:
                duplicate_groups.append((path1, duplicates))
                processed_files.add(path1)
                print(f"중복 그룹 생성: {os.path.basename(path1)} 외 {len(duplicates)}개 파일")
            # 같은 이름을 가진 파일들끼리 그룹화하는 코드 제거
        
        return duplicate_groups 