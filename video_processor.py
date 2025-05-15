import os
import numpy as np
from PIL import Image
import av
import io
import tempfile

class VideoProcessor:
    """비디오 파일에서 프레임을 추출하고 처리하는 클래스"""
    
    @staticmethod
    def check_av():
        """PyAV 라이브러리가 정상적으로 로드되었는지 확인합니다"""
        try:
            import av
            return True
        except ImportError as e:
            print(f"PyAV 확인 오류: {e}")
            return False
    
    @staticmethod        
    def get_video_duration(video_path):
        """비디오 파일의 재생 시간을 초 단위로 반환합니다"""
        if not os.path.exists(video_path):
            return 0
            
        try:
            with av.open(video_path) as container:
                # 비디오 스트림 찾기
                stream = next((s for s in container.streams if s.type == 'video'), None)
                if stream is None:
                    return 0
                
                # 비디오 스트림 시간 정보 계산
                duration = float(stream.duration * stream.time_base)
                return duration
        except Exception as e:
            print(f"비디오 길이 확인 오류: {e}")
            return 0
    
    def extract_frame_at_second(self, video_path, position_seconds, output_size=(16, 16)):
        """비디오의 특정 시간(초)에서 프레임을 추출하고 그레이스케일로 변환합니다"""
        if not os.path.exists(video_path):
            return None
            
        try:
            with av.open(video_path) as container:
                # 비디오 스트림 찾기
                stream = next((s for s in container.streams if s.type == 'video'), None)
                if stream is None:
                    return None
                
                # 시간을 타임스탬프로 변환
                timestamp = int(position_seconds / stream.time_base)
                
                # 원하는 위치로 이동
                container.seek(timestamp, any_frame=False, backward=True, stream=stream)
                
                # 프레임 추출
                for frame in container.decode(stream):
                    if frame.pts * stream.time_base >= position_seconds:
                        # PIL Image로 변환
                        img = frame.to_image()
                        # 크기 조정
                        img = img.resize(output_size)
                        # 그레이스케일로 변환
                        img = img.convert('L')
                        # NumPy 배열로 변환
                        return np.array(img)
            
            return None
        except Exception as e:
            print(f"프레임 추출 오류: {e}")
            return None
            
    def extract_frame_at_percent(self, video_path, position_percent, output_size=(16, 16)):
        """비디오의 특정 퍼센트 위치에서 프레임을 추출하고, 그레이스케일로 변환합니다"""
        duration = self.get_video_duration(video_path)
        if duration <= 0:
            return None
            
        # 퍼센트를 초로 변환
        position_seconds = duration * (position_percent / 100.0)
        return self.extract_frame_at_second(video_path, position_seconds, output_size)
    
    def extract_multiple_frames(self, video_path, positions_percent, output_size=(16, 16)):
        """비디오에서 여러 위치의 프레임을 추출합니다"""
        frames = []
        for pos in positions_percent:
            frame = self.extract_frame_at_percent(video_path, pos, output_size)
            if frame is not None:
                frames.append(frame)
        return frames if frames else None
        
    @staticmethod
    def is_frame_too_dark(frame, threshold=20):
        """프레임이 너무 어두운지 확인합니다 (평균 밝기가 threshold 미만이면 어두움)"""
        if frame is None:
            return True
        avg_brightness = np.mean(frame)
        return avg_brightness < threshold
        
    @staticmethod
    def calculate_frame_similarity(frame1, frame2):
        """두 프레임 간의 유사도를 계산합니다 (0-100%, 높을수록 유사)"""
        if frame1 is None or frame2 is None or frame1.shape != frame2.shape:
            return 0
            
        # 절대 차이의 평균 계산
        diff = np.abs(frame1.astype(float) - frame2.astype(float)).mean()
        # 차이를 0-100 범위의 유사도로 변환
        max_pixel_value = 255.0
        similarity = 100.0 * (1.0 - (diff / max_pixel_value))
        return similarity 