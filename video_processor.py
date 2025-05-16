import os
import numpy as np
from PIL import Image
import av
import io
import tempfile
import time

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
    def is_webp_animation(file_path):
        """파일이 WebP 애니메이션인지 확인합니다"""
        if not os.path.exists(file_path):
            return False
            
        _, ext = os.path.splitext(file_path.lower())
        if ext != '.webp':
            return False
            
        try:
            with Image.open(file_path) as img:
                # n_frames 속성 확인
                try:
                    if hasattr(img, 'n_frames') and img.n_frames > 1:
                        return True
                except AttributeError:
                    pass
                
                # seek 메서드로 확인
                try:
                    img.seek(1)  # 두 번째 프레임 확인
                    return True  # 두 번째 프레임이 있으면 애니메이션
                except EOFError:
                    return False  # 두 번째 프레임이 없으면 정적 이미지
        except Exception as e:
            print(f"WebP 확인 오류: {file_path} - {e}")
            return False
            
    def extract_webp_frames(self, webp_path, positions_percent, output_size=(16, 16)):
        """WebP 애니메이션에서 프레임을 추출합니다"""
        if not os.path.exists(webp_path) or not self.is_webp_animation(webp_path):
            return None
            
        try:
            frames = []
            with Image.open(webp_path) as img:
                # 총 프레임 수 확인
                try:
                    frame_count = getattr(img, 'n_frames', 0)
                    if frame_count <= 0:
                        # n_frames가 없거나 0이면 수동으로 프레임 수 계산
                        frame_count = 1
                        try:
                            while True:
                                img.seek(frame_count)
                                frame_count += 1
                        except EOFError:
                            pass  # 마지막 프레임에 도달
                except Exception as e:
                    print(f"WebP 프레임 수 확인 오류: {e}")
                    frame_count = 0
                    
                if frame_count <= 0:
                    return None
                    
                print(f"WebP 애니메이션 프레임 수: {frame_count}")
                
                # 위치 백분율에 해당하는 프레임 인덱스 계산
                frame_indices = [min(int(pos * frame_count / 100), frame_count - 1) for pos in positions_percent]
                
                # 중복 제거
                frame_indices = list(set(frame_indices))
                
                # 프레임 추출
                for idx in frame_indices:
                    try:
                        img.seek(idx)
                        frame = img.convert('L').resize(output_size)
                        frames.append(np.array(frame))
                    except Exception as e:
                        print(f"WebP 프레임 {idx} 추출 오류: {e}")
                        
                # 최소 3개의 프레임 확보
                if len(frames) < 3 and frame_count > 0:
                    additional_indices = list(range(0, frame_count, max(1, frame_count // 5)))[:5]
                    for idx in additional_indices:
                        if len(frames) >= 3:
                            break
                        if idx not in frame_indices:
                            try:
                                img.seek(idx)
                                frame = img.convert('L').resize(output_size)
                                frames.append(np.array(frame))
                            except Exception as e:
                                print(f"WebP 추가 프레임 {idx} 추출 오류: {e}")
                                
                # 여전히 프레임이 부족하면 첫 프레임을 복제
                while len(frames) < 3 and frames:
                    frames.append(frames[0].copy())
                    
            return frames if frames else None
                
        except Exception as e:
            print(f"WebP 프레임 추출 중 오류: {e}")
            return None
    
    @staticmethod        
    def get_video_duration(video_path):
        """비디오 파일의 재생 시간을 초 단위로 반환합니다"""
        if not os.path.exists(video_path):
            return 0
            
        # WebP 애니메이션인 경우 임의의 지속 시간 반환
        if os.path.splitext(video_path.lower())[1] == '.webp':
            try:
                with Image.open(video_path) as img:
                    if hasattr(img, 'n_frames') and img.n_frames > 1:
                        return float(img.n_frames) * 0.1  # 프레임당 0.1초로 가정
            except Exception:
                pass
            
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
                
                # 프레임 추출 (최대 10프레임까지 확인)
                for i, frame in enumerate(container.decode(stream)):
                    if i >= 10:  # 최대 10프레임까지만 확인
                        break
                        
                    if frame.pts * stream.time_base >= position_seconds:
                        # PIL Image로 변환
                        img = frame.to_image()
                        # 크기 조정
                        img = img.resize(output_size)
                        # 그레이스케일로 변환
                        img = img.convert('L')
                        # NumPy 배열로 변환
                        return np.array(img)
            
            # 적절한 프레임을 찾지 못한 경우 첫 번째 프레임 반환 시도
            try:
                with av.open(video_path) as container:
                    stream = next((s for s in container.streams if s.type == 'video'), None)
                    if stream is None:
                        return None
                        
                    container.seek(0)
                    for frame in container.decode(stream):
                        img = frame.to_image()
                        img = img.resize(output_size)
                        img = img.convert('L')
                        return np.array(img)
            except:
                pass
                
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
        # WebP 애니메이션인 경우 특수 처리
        if os.path.splitext(video_path.lower())[1] == '.webp' and self.is_webp_animation(video_path):
            print(f"WebP 애니메이션 특수 처리: {os.path.basename(video_path)}")
            return self.extract_webp_frames(video_path, positions_percent, output_size)
        
        frames = []
        for pos in positions_percent:
            frame = self.extract_frame_at_percent(video_path, pos, output_size)
            if frame is not None:
                frames.append(frame)
        
        # 최소 3개의 프레임 확보 시도 (기존 방식 개선)
        if len(frames) < 3:
            # 더 많은 위치에서 시도
            additional_positions = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
            for pos in additional_positions:
                if pos not in positions_percent:
                    frame = self.extract_frame_at_percent(video_path, pos, output_size)
                    if frame is not None:
                        # 이미 추출된 프레임과 너무 유사한지 확인 (중복 프레임 방지)
                        is_duplicate = False
                        for existing_frame in frames:
                            similarity = self.calculate_frame_similarity(existing_frame, frame)
                            if similarity > 95:  # 95% 이상 유사하면 중복으로 간주
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            frames.append(frame)
                            if len(frames) >= 3:  # 최소 3개 확보되면 중단
                                break
        
        # 여전히 프레임이 부족한 경우 (최소 3개 필요)
        if frames and len(frames) < 3:
            try:
                # 단순 복제 대신 프레임 변형을 통해 다양성 추가
                while len(frames) < 3:
                    # 기존 프레임에서 왼쪽/오른쪽/위/아래 일부를 크롭하여 다른 프레임처럼 만듦
                    base_frame = frames[0].copy()
                    height, width = base_frame.shape
                    
                    # 첫 번째 추가 프레임: 왼쪽 3/4 사용
                    if len(frames) == 1:
                        new_frame = base_frame[:, :int(width*0.75)]
                        # 원래 크기로 리사이즈
                        new_frame = np.array(Image.fromarray(new_frame).resize(output_size))
                        frames.append(new_frame)
                    # 두 번째 추가 프레임: 오른쪽 3/4 사용
                    elif len(frames) == 2:
                        new_frame = base_frame[:, int(width*0.25):]
                        # 원래 크기로 리사이즈
                        new_frame = np.array(Image.fromarray(new_frame).resize(output_size))
                        frames.append(new_frame)
            except Exception as e:
                print(f"프레임 변형 오류: {e}")
                # 변형에 실패하면 마지막 수단으로 복제
                while len(frames) < 3 and frames:
                    # 가장 덜 유사한 프레임을 찾아 복제
                    if len(frames) == 1:
                        # 첫 프레임을 약간 어둡게 만들어 복제
                        new_frame = frames[0].copy() * 0.8
                        frames.append(new_frame.astype(np.uint8))
                    elif len(frames) == 2:
                        # 첫 프레임을 약간 밝게 만들어 복제
                        new_frame = np.minimum(frames[0].copy() * 1.2, 255)
                        frames.append(new_frame.astype(np.uint8))
        
        # 프레임이 전혀 없는 경우 (파일 접근 실패 등)
        if not frames:
            print(f"프레임 추출 실패: {os.path.basename(video_path)}")
            return None
                
        return frames
        
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
        if frame1 is None or frame2 is None:
            return 0
            
        # 프레임 크기가 다른 경우 리사이즈하여 비교
        if frame1.shape != frame2.shape:
            try:
                # 첫 번째 프레임 크기에 맞춰 두 번째 프레임 리사이즈
                frame2_resized = np.array(Image.fromarray(frame2).resize(
                    (frame1.shape[1], frame1.shape[0])
                ))
                frame2 = frame2_resized
            except Exception as e:
                print(f"프레임 리사이즈 오류: {e}")
                return 0
        
        try:
            # 절대 차이의 평균 계산
            diff = np.abs(frame1.astype(float) - frame2.astype(float)).mean()
            # 차이를 0-100 범위의 유사도로 변환
            max_pixel_value = 255.0
            similarity = 100.0 * (1.0 - (diff / max_pixel_value))
            
            return similarity
        except Exception as e:
            print(f"유사도 계산 오류: {e}")
            return 0 